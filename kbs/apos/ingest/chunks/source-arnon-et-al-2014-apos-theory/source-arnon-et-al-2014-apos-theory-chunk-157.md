---
id: source-arnon-et-al-2014-apos-theory-chunk-157
title: Arnon et al. (2014) APOS Theory · fragmento 157 (p. 70)
source: source-arnon-et-al-2014-apos-theory
index: 157
start: 172995
end: 174166
page: 70
---

# Arnon et al. (2014) APOS Theory · fragmento 157 (p. 70)

## Texto

For the
set of prime numbers less than 100, the screen display for returning the set as a list is
> !setrandom off
> {x : x in {2,3..100} | not exists y in {2,3..x-1} | x mod
y ¼ 0};
{2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47,
53, 59, 61, 67, 71, 73, 79, 83, 89, 97};
or
> !setrandom on
> {x : x in {2,3..100} | not exists y in {2,3..x-1} | x mod
y ¼ 0};
{17, 19, 29, 23, 11, 13, 7, 5, 2, 3, 41, 37, 31, 47, 43, 53,
59, 61, 67, 71, 73, 97, 89, 83, 79};
The command !setrandom off ensures that the elements of the set will be
listed in numerical order, while the command !setrandom on returns the listing
of the elements in random order.
The syntax for sets of tuples is treated in a similar way. In standard mathematical
notation, the set-builder representation for Z
3
2 , the set of all three tuples with entries
in Z2 (the set of all integers modulo 2), is
Z3
2 ¼ a; b; cðÞ : a; b; c 2 0; 1fgfg :
In ISETL, the set is represented almost identically:
Z2_3:¼{[a,b,c] : a,b,c in {0,1}};
There is, however, a subtle, though important, difference between the two
representations. In the mathematical representation, the ordered triples appear
with parentheses.
