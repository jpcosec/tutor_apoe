---
id: source-arnon-et-al-2014-apos-theory-chunk-213
title: Arnon et al. (2014) APOS Theory · fragmento 213 (p. 95)
source: source-arnon-et-al-2014-apos-theory
index: 213
start: 233413
end: 234583
page: 95
---

# Arnon et al. (2014) APOS Theory · fragmento 213 (p. 95)

## Texto

After making these computations, they explained why each string,
obtained either by hand or by application of the ISETL command, is equal to the
fraction on which they performed long division. The ISETL code for making these
conversions follows:
> Frac2Dec(2,7);
"0.2(857142)";
>
> Frac2Dec(4,9);
"0.4(4)";
>
> Frac2Dec(3,11);
"0.2(72)";
>
> Frac2Dec(2,13);
"0.1(538461)";
5.4 Application of the ACE Teaching Cycle in a Unit on Repeating Decimals 85

These lines of code verify the results of the long division carried out by hand.
The reverse process, moving from decimal string to fraction, is illustrated next:
> Dec2Frac("0.2(857142)");
[2, 7];
>
> Dec2Frac("0.4(4)");
[4, 9];
>
> Dec2Frac("0.2(72)");
[3, 11];
>
> Dec2Frac("0.1(538461)");
[2, 13];
In a second series of activities, students performed a number of arithmetic and
ordering operations, ﬁrst on strings and then on the corresponding fraction/integer
representations. They completed this work by hand and then used commands from
the ISETL decimal expansion package to check their answers. In each case, they
reﬂected on whether the fraction/integer representations are equal to the
corresponding strings.
