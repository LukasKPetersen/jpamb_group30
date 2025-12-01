#!/usr/bin/env bash
awk -F'->' '
{
  # Trim whitespace around the two sides
  gsub(/^[ \t]+|[ \t]+$/, "", $1)
  gsub(/^[ \t]+|[ \t]+$/, "", $2)

  sig = $1

  # Drop the concrete input arguments, keep only the method signature
  # e.g. "…arrayNotEmpty:([I)V       ([I:1])" -> "…arrayNotEmpty:([I)V"
  sub(/[ \t]+\(.*\)$/, "", sig)

  # Key = "method signature -> result"
  key = sig " -> " $2

  # Only count each unique (method + result) once
  if (!seen[key]++) {
    # Extract group name: jpamb.cases.Arrays.arrayNotEmpty...
    n = split(sig, parts, ".")
    group = (n >= 3 ? parts[3] : "UNKNOWN")
    count[group]++
    total++
  }
}
END {
  for (g in count)
    printf "%s: %d\n", g, count[g]
  printf "Total: %d\n", total
}' target/stats/cases.txt | sort