---
id: source-arnon-et-al-2014-apos-theory-chunk-159
title: Arnon et al. (2014) APOS Theory · fragmento 159 (p. 71)
source: source-arnon-et-al-2014-apos-theory
index: 159
start: 175185
end: 176162
page: 71
---

# Arnon et al. (2014) APOS Theory · fragmento 159 (p. 71)

## Texto

Lines without
prompts indicate what the computer returns as output
2:
Line 1: > 7+18;
Line 2: 25;
Line 3: > 13*(233.8)
Line 4: >> ;
Line 5: 3039.400;
Line 6: > !rational off
Line 7: > 27/36;
Line 8: 0.750;
Line 9: > !rational on
Line 10: > 27/36;
Line 11: 3/4;
Line 12: > 5-9
Line 13: >> ;
Line 14: -4;
The command !rational off (Line 6) instructs ISETL to return rational
numbers in decimal form (the number of decimal places can be set using a simple
command), while the command !rational on (Line 9) calls for fractional
representations.
ISETL supports variables, which are case sensitive and deﬁned using the
symbol:¼. For example, entry of x:¼2; sets the variable x equal to 2. When
the variable x is called (indicated in ISETL by x;), ISETL returns 2:
> x:¼2;
> x;
2;
2 The notation Line # does not actually appear on an ISETL screen. It is being used for convenience
here and in other examples with longer lines of code.
5.2 ISETL: A Mathematical Programming Language 61
