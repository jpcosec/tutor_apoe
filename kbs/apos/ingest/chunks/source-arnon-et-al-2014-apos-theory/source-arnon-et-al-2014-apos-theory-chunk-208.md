---
id: source-arnon-et-al-2014-apos-theory-chunk-208
title: Arnon et al. (2014) APOS Theory · fragmento 208 (p. 93)
source: source-arnon-et-al-2014-apos-theory
index: 208
start: 228097
end: 229266
page: 93
---

# Arnon et al. (2014) APOS Theory · fragmento 208 (p. 93)

## Texto

The other two
funcs, EqualString, which tests whether two decimal strings are equal, and
GreatString, which tests whether the ﬁrst entry is larger than the second, are
also Boolean operators.
The remaining activities emphasized the connection between representations,
that is, that each fraction or integer has a corresponding decimal expansion.
The researcher-developed decimal expansion package included a func called
Dec2Frac that accepts a string and returns the fraction that corresponds to the
given string. The command Frac2Dec does the reverse—given a fraction, it
returns the corresponding decimal expansion. For the given list of 16 strings,
students were asked to think of a number (fraction or integer) that would correspond
to each string. They then applied Dec2Frac to each string in the list to test their
predictions. The students were then asked to perform long division on the fractions
returned by ISETL to verify by hand the correspondence revealed by Dec2Frac.
In the code given below, the func Dec2Frac shows that the repeating decimal
0:23/C224 corresponds to the fraction
211
900 and that the decimal 0:7867 corresponds to the
fraction 262
333 .
