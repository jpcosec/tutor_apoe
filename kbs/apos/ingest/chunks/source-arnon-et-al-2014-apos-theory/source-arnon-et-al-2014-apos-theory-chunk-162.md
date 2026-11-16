---
id: source-arnon-et-al-2014-apos-theory-chunk-162
title: Arnon et al. (2014) APOS Theory · fragmento 162 (p. 73)
source: source-arnon-et-al-2014-apos-theory
index: 162
start: 178452
end: 179641
page: 73
---

# Arnon et al. (2014) APOS Theory · fragmento 162 (p. 73)

## Texto

The code represents
a function f that accepts a number x and returns the sum of x and 3 modulo 6. Line
5 gives the code necessary to evaluate f when x ¼ 4. The actual value of f at x ¼ 4
is given in Line 6.
Line 1: > f:¼func(x);
Line 2: >> return (x+3) mod 6;
Line 3: >> end;
Line 4: >
Line 5: > f(4);
Line 6: 1;
A proc or procedure is the same as a func except that it has no return
statement and does not return a value. It is used to perform internal operations.
In the example below, the proc called SetNot accepts a tuple of length 2 called
pair. The variable G, the ﬁrst component of the tuple (a set, deﬁned in Line 7), is
assigned the value of pair(1), and the variable o, the second component of
the tuple (a func, deﬁned in Lines 8–11), is assigned the value of pair(2).
SetNot assigns to the variable e the identity with respect to o and G. The value
of the variable inv is a set that consists of all the tuples of the form [g, g’] ,
where g is an element of G and g’ is the left inverse of g with respect to the
operation o.T h e“.o” notation that appears in Lines 3 and 4 in the equations x. o
g ¼ g and g’ .o g ¼
e indicates use of .o as a binary operation on G in inﬁx form.
