---
id: source-arnon-et-al-2014-apos-theory-chunk-161
title: Arnon et al. (2014) APOS Theory · fragmento 161 (p. 72)
source: source-arnon-et-al-2014-apos-theory
index: 161
start: 177341
end: 178451
page: 72
---

# Arnon et al. (2014) APOS Theory · fragmento 161 (p. 72)

## Texto

The beginning statement is of the form for [element(s) in
some set] do, and the concluding statement is given by the end for command.
In the sample code below, Lines 1 and 2 deﬁne variables that will be used in
execution of the for loop: the set S, which represents the ﬁrst three counting
numbers, and the variable a, which is set equal to 0 (as an initial value). The for
loop, given in Lines 3 through 5, builds a sum, represented by the variable
a, consisting of all possible pairs of elements from S. The value of a is reported
in Line 7 as a result of the ISETL “call” for the value of the variable, which appears
in Line 6.
Line 1: > S:¼{1..3};
Line 2: > a:¼0;
Line 3: > for x, y in S do
Line 4: >> a:¼a+x+y;
Line 5: >> end for;
Line 6:
> a;
Line 7: 36;
Important mathematical objects such as functions can be deﬁned and evaluated
in ISETL. In the following case, the command func (Line 1) accepts variable(s),
62 5 The Teaching of Mathematics Using APOS Theory

whose values can be numbers, sets, tuples, and even other funcs. It includes a
return statement (Line 2) that yields the output of the func.
