---
id: source-arnon-et-al-2014-apos-theory-chunk-179
title: Arnon et al. (2014) APOS Theory · fragmento 179 (p. 81)
source: source-arnon-et-al-2014-apos-theory
index: 179
start: 196666
end: 197794
page: 81
---

# Arnon et al. (2014) APOS Theory · fragmento 179 (p. 81)

## Texto

Sample Code:
Line 1: > S3:¼{[a,b,c] : a,b,c in {1..3} | #{a,b,c}¼ 3};
Line 2: > comp:¼func(p,q);
Line 3: >> if (p in S3 and q in S3) then
Line 4: >> return [p(q(i)) : i in [1..3]];
Line 5: >> end;
Line 6: >> end;
Line 9: >
Line 10: > is_commutative:¼func(S,op);
Line 11: >> return forall x,y in S : x .op y ¼ y .op x;
Line 12: >> end;
Line 13: >
Line 14: > is_commutative(G,o);
Line 15: false;
The func is_commutative (lines 10–12) is a Boolean-valued function that
accepts a set S and a binary operation op and checks whether the operation op
deﬁned on S is commutative. In line 14, the func is_commutative is applied
to the set S3 and to the operation comp. The result of that test appears in Line 15.
Several kinds of binary operations appear in ISETL as predeﬁned operations.
These include mod, div, min, max, and, or. Students work with these without
explicit mention that they are binary operations. Activities involving these
commands are designed to help students to construct a binary operation Schema.
In alignment with standard mathematical notation, and as mentioned earlier,
ISETL supports the use of inﬁx notation.
