---
id: source-arnon-et-al-2014-apos-theory-chunk-182
title: Arnon et al. (2014) APOS Theory · fragmento 182 (p. 83)
source: source-arnon-et-al-2014-apos-theory
index: 182
start: 200037
end: 201057
page: 83
---

# Arnon et al. (2014) APOS Theory · fragmento 182 (p. 83)

## Texto

Line 5: > S3:¼{[a,b,c] : a,b,c in {1,2,3} : #{1,2,3}¼ 3};
Line 6: >
Line 7: > comp:¼func(p,q);
Line 8: >> return [p(q(i)) : i in [1..3]];
Line 9: >> end;
Line 10: >
Line 11: > is_associative(S3,comp);
Line 12: true;
The four instances of the coordination of set, binary operation, and axiom that
underlie the closure, associativity, existence of identity, and existence of inverses
axioms are then coordinated into a total Process of satisfying the axioms for a
group. This mental construction is advanced by having students write a func
called is_group.T h i sfunc accepts a set and a binary operation and returns a
Boolean value. One possibility for is_group is the following:
> is_group:¼func(G,op);
>> return is_closed(G,op) and
is_associative(G,op) and
has_identity(G,op) and
has_inverses(G,op);
>> end;
As students apply is_group to different set and binary operation pairs, they
build a collection of examples and non-examples of groups. Consideration of
different examples supports coherence of the group Schema.
