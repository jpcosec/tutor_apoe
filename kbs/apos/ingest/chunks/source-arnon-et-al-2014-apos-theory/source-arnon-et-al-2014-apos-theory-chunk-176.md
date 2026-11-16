---
id: source-arnon-et-al-2014-apos-theory-chunk-176
title: Arnon et al. (2014) APOS Theory · fragmento 176 (p. 80)
source: source-arnon-et-al-2014-apos-theory
index: 176
start: 193694
end: 194838
page: 80
---

# Arnon et al. (2014) APOS Theory · fragmento 176 (p. 80)

## Texto

The func tests whether the binary operation op
deﬁned on S is commutative. The func is called for the set G and operation o.
Since o is commutative, the func returns true (Line 15). Since the func
is_commutative is an Action applied to its inputs, determining the code for
is_commutative and then applying it may encourage encapsulation of the set
and binary operation concepts.
5.3.1.2 Binary Operation
For a speciﬁc ﬁnite set, a speciﬁc binary operation is an Action applied to the set.
Writing a func in ISETL may lead to interiorization of that Action. An example of
such an activity follows:
Example: For the set S3 of all permutations on three elements, write the code for a func
comp that accepts two elements from S3 and returns the composition of those elements.
Line 1: > S3:¼{[a,b,c] : a,b,c in {1..3} | #{a,b,c} ¼ 3};
Line 2: > comp:¼func(p,q);
Line 3: >> if (p in S3 and q in S3) then
Line 4: >> return [p(q(i)) : i in [1..3]];
Line 5: >> end;
Line 6: >> end;
The set S3 is deﬁned in Line 1. Lines 2 through 6 give the ISETL code for the
func comp, which accepts two elements ofS3 and returns the composition of those
permutations.
