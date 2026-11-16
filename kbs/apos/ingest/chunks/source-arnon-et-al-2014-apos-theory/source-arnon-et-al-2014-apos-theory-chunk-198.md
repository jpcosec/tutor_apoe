---
id: source-arnon-et-al-2014-apos-theory-chunk-198
title: Arnon et al. (2014) APOS Theory · fragmento 198 (p. 88)
source: source-arnon-et-al-2014-apos-theory
index: 198
start: 217166
end: 218327
page: 88
---

# Arnon et al. (2014) APOS Theory · fragmento 198 (p. 88)

## Texto

This means ﬁnite or inﬁnite
sequences of digits that correspond to the decimal expansion of a rational number.
78 5 The Teaching of Mathematics Using APOS Theory

5.4.1.1 Activities
In the computer lab, students completed activities using eight preloaded decimal
expansions6 whose identity 7 was purposely left a mystery. In the activities with
these strings, students made extensive use of a predeﬁned func called View. The
View command works in two ways: View(ds,n) yields the nth place of the
decimal string ds and View(ds,n,k) returns the nth through kth entries of ds.
The underlying idea behind the func View was its potential to support interiori-
zation of the Action of listing the digits of a decimal string. This goal may be more
apparent by considering a speciﬁc example. To determine the identity of the
mystery string m5, one might apply View to several individual values of n:
> View(m5,1);
"1";
> View(m5,2);
"0";
> View(m5,3);
"3";
> View(m5,4);
"5";
> View(m5,5);
"8";
> View(m5,6);
"5";
> View(m5,7);
"8";
> View(m5,-1);
"1";
> View(m5,-2);
"2";
> View(m5,-3);
"";
For positive values of n, View returns the nth place after the decimal point.
