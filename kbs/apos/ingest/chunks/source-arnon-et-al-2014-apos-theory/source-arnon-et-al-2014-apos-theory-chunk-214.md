---
id: source-arnon-et-al-2014-apos-theory-chunk-214
title: Arnon et al. (2014) APOS Theory · fragmento 214 (p. 96)
source: source-arnon-et-al-2014-apos-theory
index: 214
start: 234584
end: 235602
page: 96
---

# Arnon et al. (2014) APOS Theory · fragmento 214 (p. 96)

## Texto

For example, for sums, students were given the decimals
0.3125 and 0 :/C221 and their corresponding fraction representations
5
16 and 1
9
. They
applied Dec2Frac to each decimal and Frac2Dec to each fraction to see the
connection between the different representations. Then, they found the sums, ﬁrst
for the two decimals and then for the two fractions. After making these calculations,
they applied Frac2Dec and Dec2Frac to their results to see that the operations
yield equivalent results regardless of the representation being worked with. The
ISETL code is shown below:
> Dec2Frac("0.3125(0)");
[5, 16];
>
> Dec2Frac("0.1(1)");
[1, 9];
>
> "0.3125(0)" .AddString "0.1(1)";
"0.4236(1)";
>
> 5/16 + 1/9;
61/144;
>
> Dec2Frac("0.4236(1)");
[61, 144];
>
> Frac2Dec(61,144);
"0.4236(1)";
86 5 The Teaching of Mathematics Using APOS Theory

These lines of codes are reﬂected in a commutative progression illustrated in
Fig. 5.5.
Figure 5.5 shows a generalization of the steps of the procedure given in the ISETL
example.
