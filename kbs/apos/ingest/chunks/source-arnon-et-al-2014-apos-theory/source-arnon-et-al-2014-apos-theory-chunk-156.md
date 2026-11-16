---
id: source-arnon-et-al-2014-apos-theory-chunk-156
title: Arnon et al. (2014) APOS Theory · fragmento 156 (p. 69)
source: source-arnon-et-al-2014-apos-theory
index: 156
start: 171861
end: 172994
page: 69
---

# Arnon et al. (2014) APOS Theory · fragmento 156 (p. 69)

## Texto

The syntax of the language is very close to standard mathematical notation, the
language supports certain mathematical features, and all data types can be acted
on as objects. Each of these aspects of ISETL is discussed in Sects. 5.2.2–5.2.4.
Use of ISETL as a pedagogical tool is considered in Sect. 5.2.5.
5.2.2 The Syntax Is Close to Standard Mathematical
Notation
In ISETL, syntax resembles standard mathematical notation. For example, in
mathematical set former notation, the prime numbers from 2 to 100 can be
represented in the following way:
5.2 ISETL: A Mathematical Programming Language 59

fx : x 2 2; 3; ... ; 100fg jð 6 9 y 2 2; 3; ... ; x /C0 1fg 3 x mod y ¼ 0g:
The ISETL representation is nearly identical:
{x : x in {2..100} | (not exists y in {2,3..x-1} | x mod y ¼0}.
In ISETL the word “in” stands for the “element of” symbol 2 , the phrase
“not exists” replaces the “not exists” symbol 6 9, and the character “|” represents
the “such that” symbol 3 .
To return a set in list form, the user types the code for the set former at the ISETL
prompt >, places a semicolon at the end of the code, and then presses enter.
