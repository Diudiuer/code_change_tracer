int b()
{
    int x = 5;
    x *= 3;
    return x;
}
int b2()
{
    int x = 5;
    x++;
    return x;
}

int test()
{
    int s = b();
    return 0;
}

int test1()
{
    int s = b2();
    return 0;
}