---
id: source-arnon-et-al-2014-apos-theory-chunk-181
title: Arnon et al. (2014) APOS Theory · fragmento 181 (p. 82)
source: source-arnon-et-al-2014-apos-theory
index: 181
start: 198960
end: 200035
page: 82
---

# Arnon et al. (2014) APOS Theory · fragmento 181 (p. 82)

## Texto

This
coordinated Process is then applied to a particular set and binary operation.
This involves de-encapsulation of the set and binary operation Objects followed
by coordination of the set, binary operation, and axiom Processes to establish the
validity of an axiom for a given set, binary operation pair. These types of mental
constructions are facilitated by activities in which students write funcs such as
is_closed, is_associative, has_identity, and has_inverses.
Each func accepts a set and a binary operation as inputs and returns a Boolean
result. Students test these funcs on speciﬁc set and binary operation pairs. For
example, to test associativity (Lines 1–3) of the function composition operation
comp deﬁned on S3 (Line 5), students would enter the code is_associative
(S3,comp) (Line 11), where S3 denotes the set and comp (Line 7–9) represents
the composition operation:
Line 1: > is_associative:¼func(G,op);
Line 2: >> return forall x,y,z in G | (x .op y) .op z ¼ x .op
(y .op z);
Line 3: >> end;
Line 4: >
72 5 The Teaching of Mathematics Using APOS Theory
