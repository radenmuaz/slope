import slope
from slope import environment as sev

x = sev.ones((3,))
x_dot = sev.ones((3,))

def f(x):
    # y = x
    y = sev.concatenate((x,x))
    # y = y.sum()
    breakpoint()
    return y

out = f(x)
# out, out_deriv = slope.jvp(f, (x,), (x_dot,))
print(out)