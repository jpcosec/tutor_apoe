---
id: source-arnon-et-al-2014-apos-theory-chunk-163
title: Arnon et al. (2014) APOS Theory · fragmento 163 (p. 73)
source: source-arnon-et-al-2014-apos-theory
index: 163
start: 179642
end: 180792
page: 73
---

# Arnon et al. (2014) APOS Theory · fragmento 163 (p. 73)

## Texto

The inﬁx notation can be used with any func of two variables in ISETL. If o is a
func that accepts two inputs a and b, the call for o can be expressed as o(a,b) or
as a. ob . This latter notation acknowledges that a function of two variables
deﬁned on a set is a binary operation on that set:
Line 1: > SetNot:¼proc(pair);
Line 2: >> G:¼pair(1); o:¼pair(2);
Line 3: >> e:¼choose x in G | (forall g in G | x .o g ¼ g);
Line 4: >> inv:¼{ [ g ,c h o o s eg ’i nG|g ’. og¼ e ]:gi nG } ;
Line 5: >> end;
Line 6: > pair:¼[] ;
Line 7: > pair(1):¼{0..5};
Line 8: > pair(2):¼func(x,y);
Line 9: >> if (x in G and y in G) then
Line 10: >> return (x*y) mod 6;
Line 11: >> end;
Line 12: >> end;
Line 13: > pair;
Line 14: [{0, 1, 2, 3, 4, 5}, !func(6)!];
Line 15: > SetNot(pair);
Line 16: > G; e; inv(5); inv(2);
Line 17: {1, 0, 2, 3, 5, 4};
5.2 ISETL: A Mathematical Programming Language 63

Line 18: 1;
Line 19: 5;
Line 20: OM;
In Line 13, where pair appears, ISETL returns a tuple which consists of two
elements, the set deﬁned by pair(1) and an expression !func(6)!, which
denotes the fact that pair(2) is a func.
Line 15 denotes the “call” of SetNot for pair.
