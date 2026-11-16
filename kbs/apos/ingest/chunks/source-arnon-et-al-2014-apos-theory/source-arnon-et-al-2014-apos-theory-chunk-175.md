---
id: source-arnon-et-al-2014-apos-theory-chunk-175
title: Arnon et al. (2014) APOS Theory · fragmento 175 (p. 79)
source: source-arnon-et-al-2014-apos-theory
index: 175
start: 192525
end: 193693
page: 79
---

# Arnon et al. (2014) APOS Theory · fragmento 175 (p. 79)

## Texto

Then, write
code to determine whether the func deﬁned on G is commutative.
Line 1: > G:¼{1..12};
Line 2: > G;
Line 3: {1, 2, 4, 3, 12, 11, 10, 9, 6, 5, 8, 7};
Line 4: > o:¼func(x,y);
Line 5: >> if (x in G and y in G) then
Line 6: >> return (x*y) mod 13;
Line 7: >> end;
Line 8: >> end;
Line 9: >
5.3 Teaching and Learning Groups 69

Line10: > is_commutative:¼func(S,op);
Line11: >> return forall x,y in S : x .op y ¼ y .op x;
Line12: >> end;
Line13: >
Line14: > is_commutative(G,o);
Line15: true;
In Line 1, the set G is deﬁned. Line 2 is an ISETL call for G, which is returned in
list form in Line 3. Lines 4 through 8 give the code for the func o , which is a
binary operation deﬁned on G. In order for a student to write the func o , he/she
must write code to select two arbitrary elements from the set G and then apply the
operation to those elements. The selection of arbitrary elements constitutes an
Action applied to the set. As a result, the set must ﬁrst be encapsulated into a
mental Object so that the Action can be applied. Lines 10 through 12 are the ISETL
code for the func is_commutative . This func accepts a set S and binary
operation op deﬁned on S.
