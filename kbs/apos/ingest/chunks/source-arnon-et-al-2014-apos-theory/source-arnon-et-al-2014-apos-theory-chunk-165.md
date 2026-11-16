---
id: source-arnon-et-al-2014-apos-theory-chunk-165
title: Arnon et al. (2014) APOS Theory · fragmento 165 (p. 74)
source: source-arnon-et-al-2014-apos-theory
index: 165
start: 181633
end: 182782
page: 74
---

# Arnon et al. (2014) APOS Theory · fragmento 165 (p. 74)

## Texto

This can be seen in the following lines of code
for the func D , which accepts a function f and returns a func, which is the
difference quotient of f within 0.001 units of the value of the variable x:
> D:¼func(f);
>> return func(x);
>> return (f(x+0.001)-f(x))/0.001;
>> end;
>> end;
The func D enables ISETL to compute the difference quotient for any speciﬁed
function f at any domain point x using a difference of 0.001. For instance, if the
function f is deﬁned by f ðxÞ¼ x
2 þ 1, which would appear in ISETL as
> f:¼func(x);
>> return x**2+1;
>> end;
the call of D(f)(3); returns the value of the difference quotient for f at x ¼ 3
using a difference of 0.001:
> D(f)(3);
6.001;
A similar example is the func Sum , given by the code which follows. This
func accepts two funcs representing functions f and g and returns a func
that represents their sum, which is given by Sum, which is deﬁned in Lines 1–5.
64 5 The Teaching of Mathematics Using APOS Theory

Two particular functions f and g are deﬁned in Lines 7–13. The call for Sum, given
by Sum(f,g) (Line 15), returns the value !func(7)! (Line 16) to indicate that
Sum(f,g)is itself a func.
