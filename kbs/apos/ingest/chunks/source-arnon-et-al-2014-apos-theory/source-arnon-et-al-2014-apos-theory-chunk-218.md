---
id: source-arnon-et-al-2014-apos-theory-chunk-218
title: Arnon et al. (2014) APOS Theory · fragmento 218 (p. 98)
source: source-arnon-et-al-2014-apos-theory
index: 218
start: 238679
end: 239714
page: 98
---

# Arnon et al. (2014) APOS Theory · fragmento 218 (p. 98)

## Texto

Activity: Perform the following calculations using the ISETL code .MultString:
0:0 769230ðÞ /C2 0:/C229
(type “0.0(769230)” .MultString “0.9(9)”; and press enter)
19
15 /C2 0:/C229
(type Frac2Dec(19,15) .MultString “0.9(9)”; and press enter)
253 /C2 0:/C229
(type Frac2Dec(253,1) .MultString “0.9(9)”; and press enter)
0:2ð342Þ/C4 0:/C229
(type “0.2(342)” .DivString “0.9(9)”; and press enter)
713 /C4 0:/C229
(type Frac2Dec(713,1) .DivString “0.9(9)”; and press enter)
It would be very cumbersome to try to perform the operations above by hand. However,
it would be very easy to do them by hand if you replaced “0.9(9)” by “1.0(0)”. Explain why
or why not you think this would be correct.
MultString and DivString, two funcs included in the decimal expansion
package, accept two decimal strings and return the product and quotient, respec-
tively. Sample lines of code appear below:
> "0.0(769230)" .MultString "0.9(9)";
"0.0(769230)";
>
> "0.2(342)" .DivString "0.9(9)";
"0.2(342)";
88 5 The Teaching of Mathematics Using APOS Theory
