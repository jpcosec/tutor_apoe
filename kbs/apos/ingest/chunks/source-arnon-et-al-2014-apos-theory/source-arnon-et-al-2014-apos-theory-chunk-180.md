---
id: source-arnon-et-al-2014-apos-theory-chunk-180
title: Arnon et al. (2014) APOS Theory · fragmento 180 (p. 81)
source: source-arnon-et-al-2014-apos-theory
index: 180
start: 197795
end: 198959
page: 81
---

# Arnon et al. (2014) APOS Theory · fragmento 180 (p. 81)

## Texto

If op is any func of two variables
in ISETL, the expression a .op b may be used instead of op(a,b). For the
5.3 Teaching and Learning Groups 71

following example, add_Z20(3,5) (Lines 8–9) returns the same result as
3.add_Z20 5 (Lines 10–11):
Line 1: > Z20:¼{0..19};
Line 2: > add_Z20:¼func(x,y);
Line 3: >> if (x in Z20 and y in Z20) then
Line 4: >> return (x+y) mod 20;
Line 5: >> end;
Line 6: >> end;
Line 7: >
Line 8: > add_Z20(3,5);
Line 9: 8;
Line 10: > 3 .add_Z20 5;
Line 11: 8;
The use of inﬁx notation helps students to see that any function of two variables
deﬁned on a set is a binary operation. This is another feature of ISETL that
promotes development of a binary operation Schema.
5.3.1.3 Group Schema
A group Schema is constructed mentally through coordination of the axiom Schema
with the set and binary operations Schemas. The axiom Schema includes two
principal components:
1. Checking a property of a binary operation deﬁned on a set
2. The four axioms of the group concept constructed as Objects
The general Process of satisfying a property is coordinated with the speciﬁc
Process for the axiom, which is de-encapsulated from the axiom Object.
