---
id: source-arnon-et-al-2014-apos-theory-chunk-207
title: Arnon et al. (2014) APOS Theory · fragmento 207 (p. 93)
source: source-arnon-et-al-2014-apos-theory
index: 207
start: 226963
end: 228096
page: 93
---

# Arnon et al. (2014) APOS Theory · fragmento 207 (p. 93)

## Texto

Students ordered the
16 predeﬁned strings by hand, checked their work using comparison commands
included in the decimal expansion package, and explained how one determines
whether one string is larger than another. Another related activity called for
students to make comparisons after applying arithmetic operations. For example,
given the three decimal stringss1¼0.1(41), s2¼0.5(0),a n ds3¼0.2(132),
students determined by hand whether the sum of s1 and s3 exceeds the sum of
s1 and s2. Once they performed these computations, they tested their results
using ISETL:
> s1:¼"0.1(41)";
> s2:¼"0.5(0)";
> s3:¼"0.2(132)";
>
> (s1 .AddString s2) .LessString (s1 .AddString s3);
false;
The activity involved carrying out arithmetic operations (via AddString),
order of operations (through use of parentheses), and comparison (by application
of LessString). LessString, as the name suggests, is a Boolean operator that
tests whether the ﬁrst entry (in this case, s1 .AddString s2 ) is smaller than the
second (s1 .AddString s3 ). It was one of three comparison funcs deﬁned by
the researchers and included in the decimal expansion package.
