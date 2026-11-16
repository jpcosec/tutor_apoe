---
id: source-arnon-et-al-2014-apos-theory-chunk-160
title: Arnon et al. (2014) APOS Theory · fragmento 160 (p. 72)
source: source-arnon-et-al-2014-apos-theory
index: 160
start: 176164
end: 177340
page: 72
---

# Arnon et al. (2014) APOS Theory · fragmento 160 (p. 72)

## Texto

In addition to variables, ISETL supports Boolean operators ( and, or, not,
and impl, where impl is shorthand for implies), the usual comparison operators
(¼, /¼ (inequality), <, <¼, >, >¼), and quantiﬁers ( forall, exists,
not exists).
5.2.3 Supporting Mathematical Features
Certain control statements such as if statements and for loops can be used to
carry out mathematical procedures without the need to invoke special commands.
In Line 1 of the following example, the variable x is set equal to 4. For the if
command, which appears in Lines 2 through 6, the beginning statement is of
the form if [condition] then and ends with the line end if; . Because
the condition x > 2 is satisﬁed and precedes the condition x > 3 in Line 4 where the
elseif statement appears, ISETL only returns the ﬁrst phrase, x is larger
than 2. For a value of x less than or equal to 2, ISETL would not return anything:
Line 1: > x:¼4;
Line 2: > if x >2 then
Line 3: >> writeln "x is larger than 2";
Line 4: >> elseif x >3 then
Line 5: >> writeln "x is larger than 3";
Line 6: >> end if;
Line 7: x is larger than 2
Like an if statement, a for loop has both a beginning and a concluding
statement.
