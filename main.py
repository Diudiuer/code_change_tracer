import os
import filecmp
from pycparser import c_parser, c_ast, parse_file
from PyQt5 import QtWidgets, QtGui, QtCore
from PyQt5.QtWidgets import QFileDialog, QMessageBox, QListWidget, QListWidgetItem, QVBoxLayout, QMainWindow, QPushButton, QHBoxLayout, QTextBrowser
import difflib
import sys
from pygments import highlight
from pygments.lexers import CLexer
from pygments.formatters import HtmlFormatter

# 输入的文件夹路径
original_project_path = ''  # 原项目的文件夹路径
modified_project_path = ''  # 变更后项目的文件夹路径

def get_changed_files(original_path, modified_path):
    original_files = set()
    modified_files = set()

    # 获取所有子目录中的文件
    for root, _, files in os.walk(original_path):
        for f in files:
            relative_path = os.path.relpath(os.path.join(root, f), original_path)
            original_files.add(relative_path)

    for root, _, files in os.walk(modified_path):
        for f in files:
            relative_path = os.path.relpath(os.path.join(root, f), modified_path)
            modified_files.add(relative_path)

    # 找出新增的文件
    new_files = modified_files - original_files
    
    # 找出删除的文件
    deleted_files = original_files - modified_files

    # 找出修改的文件
    common_files = original_files & modified_files
    changed_files = [f for f in common_files if not filecmp.cmp(os.path.join(original_path, f), os.path.join(modified_path, f), shallow=False)]

    return list(new_files), list(deleted_files), changed_files

def parse_c_file(file_path):
    ast = parse_file(file_path, use_cpp=True)
    return ast

def compare_ast_nodes(node1, node2):
    if type(node1) != type(node2):
        return False
    if isinstance(node1, c_ast.Node):
        # 比较节点的所有属性
        if node1.attr_names != node2.attr_names:
            return False
        for attr in node1.attr_names:
            if getattr(node1, attr) != getattr(node2, attr):
                return False
        # 递归比较子节点
        for (child_name1, child_node1), (child_name2, child_node2) in zip(node1.children(), node2.children()):
            if child_name1 != child_name2 or not compare_ast_nodes(child_node1, child_node2):
                return False
        return True
    return node1 == node2

def get_modified_functions(original_ast, modified_ast):
    class FuncBodyVisitor(c_ast.NodeVisitor):
        def __init__(self):
            self.functions = {}

        def visit_FuncDef(self, node):
            self.functions[node.decl.name] = node.body

    original_visitor = FuncBodyVisitor()
    modified_visitor = FuncBodyVisitor()
    original_visitor.visit(original_ast)
    modified_visitor.visit(modified_ast)

    modified_functions = []
    for func_name, modified_body in modified_visitor.functions.items():
        original_body = original_visitor.functions.get(func_name)
        if original_body is None or not compare_ast_nodes(original_body, modified_body):
            modified_functions.append(func_name)

    return modified_functions

def build_call_graph(files):
    call_graph = {}

    class FuncCallVisitor(c_ast.NodeVisitor):
        def __init__(self, current_function):
            self.current_function = current_function
            self.calls = []

        def visit_FuncCall(self, node):
            if isinstance(node.name, c_ast.ID):
                self.calls.append(node.name.name)

    for file in files:
        ast = parse_c_file(file)
        for ext in ast.ext:
            if isinstance(ext, c_ast.FuncDef):
                current_function = ext.decl.name
                if current_function not in call_graph:
                    call_graph[current_function] = []
                visitor = FuncCallVisitor(current_function)
                visitor.visit(ext)
                call_graph[current_function].extend(visitor.calls)
    return call_graph

def find_ancestors(call_graph, functions):
    affected = set()
    visited = set()
    stack = list(functions)

    while stack:
        func = stack.pop()
        if func not in visited:
            visited.add(func)
            for caller, callees in call_graph.items():
                if func in callees and caller not in affected:
                    affected.add(caller)
                    stack.append(caller)
    return affected

def get_diff_text(original_text, modified_text):
    diff = difflib.unified_diff(original_text.splitlines(), modified_text.splitlines(), lineterm='')
    diff_lines = []
    line_number_original = 1
    line_number_modified = 1
    for line in diff:
        if line.startswith('+') and not line.startswith('+++'):
            diff_lines.append(f'{line[1:]}' + '\n')
            line_number_modified += 1
        elif line.startswith('-') and not line.startswith('---'):
            diff_lines.append(f'{line[1:]}' + '\n')
            line_number_original += 1
        elif line.startswith(' '):
            diff_lines.append(f'{line[1:]}' + '\n')
            line_number_original += 1
            line_number_modified += 1
    return ''.join(diff_lines)

class CodeComparisonApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.original_project_path = ''
        self.modified_project_path = ''
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle('代码比较工具')
        self.setGeometry(200, 200, 1200, 800)
        self.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4; font-family: Arial, sans-serif;")

        # 主窗口的中央控件
        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # 顶部菜单栏
        menu_bar = self.menuBar()
        menu_bar.setStyleSheet("background-color: #333333; color: #ffffff; font-weight: bold;")
        file_menu = menu_bar.addMenu('文件')
        open_original_action = file_menu.addAction('打开变更前项目')
        open_original_action.triggered.connect(self.select_original_path)
        open_original_action.setFont(QtGui.QFont('Arial', 10, QtGui.QFont.Bold))
        open_original_action.setStatusTip('选择原项目文件夹')
        open_original_action.setShortcut('Ctrl+O')
        open_modified_action = file_menu.addAction('打开变更后项目')
        open_modified_action.triggered.connect(self.select_modified_path)
        open_modified_action.setFont(QtGui.QFont('Arial', 10, QtGui.QFont.Bold))
        open_modified_action.setStatusTip('选择修改后项目文件夹')
        open_modified_action.setShortcut('Ctrl+M')
        start_tracking_action = file_menu.addAction('跟踪文件变更')
        start_tracking_action.triggered.connect(self.track_changes)
        start_tracking_action.setFont(QtGui.QFont('Arial', 10, QtGui.QFont.Bold))
        start_tracking_action.setStatusTip('跟踪项目文件的变化')
        start_tracking_action.setShortcut('Ctrl+T')

        # 左侧显示变更文件的列表
        self.change_list_widget = QListWidget()
        self.change_list_widget.setStyleSheet("background-color: #252526; color: #d4d4d4; padding: 10px; border: 1px solid #444444; font-size: 12px;")
        self.change_list_widget.setFixedWidth(400)

        # 设置变更文件数的标签（将其与文件目录窗口保持一致）
        self.change_summary_label = QtWidgets.QLabel('变更文件数: 0')
        self.change_summary_label.setStyleSheet("color: #d4d4d4; font-weight: bold; padding: 5px; background-color: #333333; border-bottom: 1px solid #444444;")
        self.change_summary_label.setFixedWidth(400)
        self.change_summary_label.setFixedHeight(30)

        # 将变更文件数标签添加到左侧布局中
        left_layout = QVBoxLayout()
        left_layout.addWidget(self.change_summary_label)
        left_layout.addWidget(self.change_list_widget)

        # 创建水平布局，将左侧变更列表和右侧文件内容展示区域分开
        horizontal_layout = QHBoxLayout()
        horizontal_layout.addLayout(left_layout)

        # 右侧文件内容展示区域
        self.file_content_widget = QtWidgets.QWidget()
        self.file_content_layout = QVBoxLayout(self.file_content_widget)

        # 文件路径显示
        self.file_path_label = QtWidgets.QLabel('文件路径: ')
        self.file_path_label.setStyleSheet("color: #d4d4d4; font-weight: bold; padding: 5px; background-color: #333333; border-bottom: 1px solid #444444;")
        self.file_path_label.setFixedHeight(30)
        self.file_content_layout.addWidget(self.file_path_label)

        # 文件内容显示区域 - 使用 QTextBrowser 以便渲染 HTML
        self.file_content_display = QTextBrowser()
        self.file_content_display.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4; padding: 10px; border: 1px solid #444444; font-size: 12px;")
        self.file_content_layout.addWidget(self.file_content_display)

        # 将文件内容展示区域添加到水平布局中
        horizontal_layout.addWidget(self.file_content_widget)

        # 添加到主布局中
        main_layout.addLayout(horizontal_layout)

    def select_original_path(self):
        self.original_project_path = QFileDialog.getExistingDirectory(self, '选择原项目路径')

    def select_modified_path(self):
        self.modified_project_path = QFileDialog.getExistingDirectory(self, '选择修改后项目路径')

    def track_changes(self):
        if not self.original_project_path or not self.modified_project_path:
            QMessageBox.warning(self, '错误', '请选择原项目和修改后项目的路径。')
            return
        self.change_summary_label.setText('正在跟踪文件变更...')

        new_files, deleted_files, changed_files = get_changed_files(self.original_project_path, self.modified_project_path)

        # 清空变更列表
        self.change_list_widget.clear()

        # 添加变更文件到列表
        total_changes = len(new_files) + len(deleted_files) + len(changed_files)
        self.change_summary_label.setText(f'变更文件数: {total_changes}')

        for file in new_files:
            item = QListWidgetItem(f"{file}  +")
            item.setForeground(QtGui.QColor("green"))
            self.change_list_widget.addItem(item)

        for file in deleted_files:
            item = QListWidgetItem(f"{file}  -")
            item.setForeground(QtGui.QColor("red"))
            self.change_list_widget.addItem(item)

        for file in changed_files:
            item = QListWidgetItem(f"{file}  ·")
            item.setForeground(QtGui.QColor("yellow"))
            self.change_list_widget.addItem(item)

        # 右侧显示选中文件的内容
        self.change_list_widget.itemClicked.connect(self.display_file_content)

    def display_file_content(self, item):
        file_path = item.text().split(' ')[0]
        try:
            if '+' in item.text():
                full_path = os.path.join(self.modified_project_path, file_path)
            elif '-' in item.text():
                full_path = os.path.join(self.original_project_path, file_path)
            else:
                original_full_path = os.path.join(self.original_project_path, file_path)
                modified_full_path = os.path.join(self.modified_project_path, file_path)
                with open(original_full_path, 'r', encoding='utf-8') as original_file:
                    original_content = original_file.read()
                with open(modified_full_path, 'r', encoding='utf-8') as modified_file:
                    modified_content = modified_file.read()
                diff_content = get_diff_text(original_content, modified_content)
                # 使用 Pygments 高亮代码
                formatter = HtmlFormatter(style='monokai', noclasses=True, linenos=True)
                highlighted_diff = highlight(diff_content, CLexer(), formatter)
                # 更新文件路径和内容显示
                relative_path = os.path.relpath(modified_full_path, start=os.path.commonpath([self.modified_project_path, self.original_project_path]))
                self.file_path_label.setText(f'文件路径: {relative_path}')
                self.file_content_display.setHtml(highlighted_diff)
        except Exception as e:
            QMessageBox.warning(self, '错误', f'无法读取文件内容: {e}')

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = CodeComparisonApp()
    window.show()
    sys.exit(app.exec_())
