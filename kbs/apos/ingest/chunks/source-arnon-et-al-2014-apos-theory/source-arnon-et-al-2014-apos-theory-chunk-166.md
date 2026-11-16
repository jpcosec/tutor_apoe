---
id: source-arnon-et-al-2014-apos-theory-chunk-166
title: Arnon et al. (2014) APOS Theory · fragmento 166 (p. 75)
source: source-arnon-et-al-2014-apos-theory
index: 166
start: 182783
end: 183772
page: 75
---

# Arnon et al. (2014) APOS Theory · fragmento 166 (p. 75)

## Texto

The call for Sum(f,g)(2) (Line 18) yields the value
of f þ gðÞ ð 2Þ (Line 19):
Line 1: > Sum:¼func(f,g);
Line 2: >> return func(x);
Line 3: >> return f(x)+g(x);
Line 4: >> end;
Line 5: >> end;
Line 6: >
Line 7: > f:¼func(x);
Line 8: >> return x**3+2;
Line 9: >> end;
Line 10: >
Line 11: > g:¼func(x);
Line 12: >> return 3*x;
Line 13: >> end;
Line 14: >
Line 15: > Sum(f,g);
Line 16: !func(7)!;
Line 17: >
Line 18: > Sum(f,g)(2);
Line 19: 16;
5.2.5 ISETL as a Pedagogical Tool
At a functional analysis conference in 1969, Dubinsky (1995) ﬁrst heard about the
programming language SETL, the forerunner to ISETL, from its developer Jack
Schwartz (see Chap. 2 for more details). Schwartz wanted to express complex
mathematical relationships using computer programs. He believed the best way to
achieve this goal was to base a programming language on fundamental mathemati-
cal concepts. This idea served as the inspiration for the development of APOS
Theory and its related research framework.
