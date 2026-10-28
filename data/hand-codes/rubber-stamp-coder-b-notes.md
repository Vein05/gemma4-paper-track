# Rubber-stamp cases: coder B notes

Source: `rubber-stamp-cases.md` (31 cases). Codes in `rubber-stamp-coder-b.csv`.

Totals: named 6, not_named 25, opposite = 1 in 21 cases (all not_named).

## Decision rules applied beyond the codebook text

- Main defect when the low-scoring judges name different defects and no defect is shared by most of them:
  the defect of the lowest-scoring judge. Where the two readings give the same code, this is noted but not flagged.
- named vs opposite: named when Gemma raises the flagged behavior as a caveat, limitation, side effect or
  departure from the old behavior (words like "redundant", "unusual", "broad stroke", "regardless of", or a
  weighed downside), even if it then accepts it. When Gemma describes the flagged code only as the correct
  working part of the fix, or asserts the contrary of the judges' claim, the code is not_named with opposite = 1
  (the codebook's "calls a keyword correct that they call wrong").

## Cases

**Case 1** `django__django-11138|gemma-4-31b|5402a395`
- Main defect: the SQLite backend still hardcodes 'UTC'; only MySQL and Oracle are changed.
- Code: not_named, opposite 0
- Quote: no mention (Gemma mentions only `fix_tz.py` and the Oracle '0:00' change).

**Case 2** `django__django-11400|gemma-4-31b|ee91b3c1`
- Main defect: the ordering passed to `field.get_choices` does not work: `ordering=None` raises a TypeError
  (glm47-flash, 0); qwen35-9b (20) says the RelatedOnlyFieldListFilter choices still are not ordered. Both
  readings give the same code.
- Code: not_named, opposite 1
- Quote: "If no `related_admin` is found, `ordering` remains `None`, allowing Django's ORM to use the model's
  default ordering." / "since it explicitly passes the `ordering` kwarg to `field.get_choices` (which was the
  primary failure point), it solves the reported bug."

**Case 3** `django__django-11555|gemma-4-31b|a7e22fac`
- Main defect: `get_order_dir` returns `field.expression` (an expression object) instead of a string field
  name, which breaks the SQL code that calls it.
- Code: not_named, opposite 1
- Quote: "This correctly identifies `OrderBy` objects ... and extracts the underlying expression and the
  direction."

**Case 4** `django__django-12754|gemma-4-31b|3952ca5d`
- Main defect: the added base-field dependencies do not give the needed operation order (glm47-flash, 20: the
  dependency logic is wrong and over-broad; qwen3-coder, 30: dependencies cannot reorder operations within one
  migration). Both readings give the same code.
- Code: not_named, opposite 1
- Quote: "the autodetector is forced to prioritize the removal ... This effectively reverses the order of
  operations to `RemoveField` then `CreateModel`"

**Case 5** `django__django-13195|gemma-4-31b|80bc3d0c`
- Main defect: the new `secure`/`httponly`/`samesite` arguments have no default or fallback, so the deletion
  header still lacks SameSite unless the caller passes it.
- Code: not_named, opposite 0
- Quote: no mention (Gemma says the patch is "allowing the caller to specify the `samesite` attribute" but never
  says SameSite is missing when the caller does not pass it).

**Case 6** `django__django-13344|gemma-4-31b|811b2eab`
- Main defect (judges split; lowest score used): `__acall__` does not await `get_response`, so the coroutine
  still reaches the first middleware (glm47-flash, 0). gpt-oss-20b (20) instead says marking every
  `sync_to_async` wrapper as async-capable is too coarse.
- Code: not_named, opposite 1
- Quote: "In `__acall__`, the response is awaited (`response = await self.get_response(request)`)"

**Case 7** `django__django-13964|gemma-4-31b|1f9e2116`
- Main defect: skipping the `setattr` leaves `product_id` empty, and nothing sets it once the product's primary
  key is assigned.
- Code: not_named, opposite 1
- Quote: "When `order.save()` is called, Django's saving logic will look at the `order.product` instance ... the
  parent will correctly resolve the foreign key during its own save process."

**Case 8** `django__django-14017|gemma-4-31b|00879f6b`
- Main defect: wrapping the `Exists` in `Q(other)` changes the tree structure (a nested Q node) instead of
  keeping `Exists` as its own node, for example by adding `__rand__`.
- Code: not_named, opposite 1
- Quote: "This approach aligns with how Django handles conditional expressions in its internal query
  construction. The logic is sound"

**Case 9** `django__django-14311|gemma-4-31b|67a401df`
- Main defect: the stray helper scripts `fix_file.py` and `fix_line_242.py`, which rewrite `autoreload.py` in a
  fragile or corrupting way.
- Code: named, opposite 0
- Quote: "bundled with two auxiliary Python scripts (`fix_file.py` and `fix_line_242.py`) that are completely
  unnecessary and potentially destructive."

**Case 10** `django__django-14792|gemma-4-31b|8d2105ad`
- Main defect (3 of 4 judges): with `startswith`, "Etc/GMT-10" is returned unchanged instead of being converted
  to the reversed offset, so the query stays wrong.
- Code: not_named, opposite 1
- Quote: "It returns the original string `"Etc/GMT-10"`, which is the correct behavior for Postgres/MySQL/Oracle
  when handling named zones."

**Case 11** `django__django-15037|gemma-4-31b|8f277655`
- Main defect: the stray `fix_inspectdb.py` patcher script (the low-score reason for qwen35-9b and qwen3-coder;
  glm-4.5 also notes it). Other defects: `to_fields` instead of `to_field` (glm-4.5), indentation (gpt-oss-20b).
- Code: named, opposite 0
- Quote: "The patch includes a file `fix_inspectdb.py`. ... While this is an unusual inclusion in a professional
  patch ..., it does not affect the actual code changes"

**Case 12** `django__django-15280|gemma-4-31b|2f7cceb2`
- Main defect (all five judges): the `__dict__.update` merge in `prefetch_one_level` blindly overwrites and
  corrupts the existing instance's state.
- Code: not_named, opposite 1
- Quote: "This logic correctly handles the identity problem while preserving the data fetched by the specific
  `Prefetch` queryset."

**Case 13** `django__django-15375|gemma-4-31b|6c814659`
- Main defect: adding `is_summary` to `Coalesce` does not fix the aggregate SQL generation; the change is in the
  wrong place.
- Code: not_named, opposite 1
- Quote: "This ensures the expression remains in the outer `SELECT` clause of the generated SQL, fixing the
  "SELECT FROM" syntax error."

**Case 14** `django__django-16032|gemma-4-31b|740b6120`
- Main defect (judges split; lowest score used): removing the `else` branch leaves the annotation columns in the
  subquery, so the error remains (gpt-oss-120b, 15). glm-4.5 (20) instead says it brings back an earlier bug
  where `.alias()` appeared in SELECT.
- Code: not_named, opposite 1
- Quote: "Removing the line ... effectively stops the incorrect pruning/retention logic that was causing the leak
  of columns into the subquery."

**Case 15** `django__django-16950|gemma-4-31b|0e837181`
- Main defect: the `fix_issue.py` string-replacement script (named by all six judges; four also call the new
  `field_name` condition wrong).
- Code: named, opposite 0
- Quote: "a "fix_issue.py" script (which is redundant/strange for a PR but doesn't affect the core logic in
  `django/forms/models.py`)"

**Case 16** `matplotlib__matplotlib-20488|gemma-4-31b|9a8ef15b`
- Main defect: `np.isnan` instead of `np.isfinite` lets infinite vmin/vmax through without the ValueError the
  tests expect.
- Code: named, opposite 0
- Quote: "By switching to `np.isnan`, the code now allows `inf` values for `t_vmin` and `t_vmax`. ... `t_value`
  becoming `0` (or `NaN` if `t_value` is also `inf`), which is generally the intended behavior"

**Case 17** `matplotlib__matplotlib-24570|gemma-4-31b|f2cbabfa`
- Main defect: the swap also reverses "left"/"right" in the shared `_get_aligned_offsets`, which breaks VPacker.
- Code: not_named, opposite 0
- Quote: no mention (Gemma discusses only top/bottom for HPacker).

**Case 18** `matplotlib__matplotlib-24637|gemma-4-31b|3fadea62`
- Main defect: the gid is set on the internal child artists (the offsetbox image and patches), which are the wrong
  targets; glm47-flash also says the calls do not take effect without `draw_children`.
- Code: not_named, opposite 1
- Quote: "the `gid` assigned to the high-level `AnnotationBbox` object is passed down to the primitive artists
  that the SVG backend uses to generate the XML."

**Case 19** `matplotlib__matplotlib-25960|gemma-4-31b|9a68fdaf`
- Main defect: `get_position` ignores `wspace` and `hspace`.
- Code: not_named, opposite 1
- Quote: "it correctly accounts for `wspace`, `hspace`, and other layout constraints."

**Case 20** `pydata__xarray-6744|gemma-4-31b|fce4bcb8`
- Main defect (judges split; lowest score used): `self.center[0]` indexes a plain bool and raises a TypeError
  (gpt-oss-120b, 15). glm47-flash (20) instead says the `stops` computation gives windows that are too small.
- Code: not_named, opposite 0
- Quote: no mention of indexing `center`.

**Case 21** `pylint-dev__pylint-7080|gemma-4-31b|383e04ac`
- Main defect (2 of 3 judges): `self.config` and `self.linter.config` are the same object, so the change does
  nothing and the recursive file discovery still ignores `ignore-paths`.
- Code: not_named, opposite 1
- Quote: "This ensures that the regex patterns defined in `ignore-paths` are actually loaded into the
  `_ignore_paths` attribute used to filter files during recursive traversal."

**Case 22** `pylint-dev__pylint-8898|gemma-4-31b|7e48b0b1`
- Main defect: CSV quoting helps only quoted regexes; unquoted (or parser-stripped) regexes with commas still
  split, and existing comma-separated configurations may break.
- Code: not_named, opposite 1
- Quote: "The use of `skipinitialspace=True` and `.strip()` ensures that whitespace around commas ... is handled,
  maintaining compatibility with previous behavior."

**Case 23** `pytest-dev__pytest-6197|gemma-4-31b|8dd6ba7c`
- Main defect (judges split; lowest score used): `__init__.py` files are still collected (gpt-oss-20b, 5).
  glm-4.5 (10) instead says explicitly given `__init__.py` files are no longer collected.
- Code: not_named, opposite 1
- Quote: "pytest will now only collect `.py` files that match the patterns defined in `python_files`" /
  "`verify_fix.py` script confirms that `__init__.py` no longer matches the default patterns."

**Case 24** `pytest-dev__pytest-7236|gemma-4-31b|36491694`
- Main defect: the `skipped_by_mark_key` store check does not detect `@unittest.skip` (glm-4.5 also says the
  name is undefined).
- Code: not_named, opposite 1
- Quote: "Pytest marks the test as skipped in its internal store. ... the patch correctly identifies the skipped
  state"

**Case 25** `sphinx-doc__sphinx-7889|gemma-4-31b|6581abe2`
- Main defect: `str(module)` does not fix the actual non-string operand (glm47-flash: `module` is already a
  string, so the cause is elsewhere; qwen35-9b: `name` can also be a TypeVar). Both judges scored 20.
- Code: not_named, opposite 1
- Quote: "the only operation failing was the string concatenation for the `__display_name__` attribute, this fix
  is minimal and targeted."

**Case 26** `sympy__sympy-12481|gemma-4-31b|f71c61e2`
- Main defect (3 of 4 judges): the patch only removes the error; `set(temp)` discards the cycle structure, so
  non-disjoint cycles are never composed.
- Code: not_named, opposite 1
- Quote: "the logic following this check handles the composition of these cycles."

**Case 27** `sympy__sympy-14711|gemma-4-31b|dcd4ed65`
- Main defect: `if other == 0: return self` is the wrong or too-narrow fix (glm47-flash: returning the vector for
  0 is semantically wrong; qwen3-coder: it handles only the exact value 0 and leaves the root cause).
- Code: not_named, opposite 1
- Quote: "This correctly handles the case where a vector is added to zero, returning the original vector, which
  is the mathematically expected behavior."

**Case 28** `sympy__sympy-15976|gemma-4-31b|5730f6cd`
- Main defect: removing the trailing-digit subscript rule from the shared `split_super_sub` changes every printer
  and breaks existing tests; the fix belongs in the MathML printer.
- Code: not_named, opposite 1
- Quote: "the upstream fix for this specific issue involved removing this exact logic to stop the automatic
  splitting of trailing digits, the patch is correct."

**Case 29** `sympy__sympy-21596|gemma-4-31b|60a4bf17`
- Main defect: replacing the subtraction with an intersection reverses the set operation, so the patch keeps the
  points it should remove (both GPT-OSS judges also flag the denominator-loop variable change).
- Code: not_named, opposite 1
- Quote: "This correctly restricts $n$ to only those values that make the imaginary part zero."

**Case 30** `sympy__sympy-23413|gemma-4-31b|b314fc72`
- Main defect: looping over all rows and returning the full matrix breaks the Hermite normal form for
  rank-deficient matrices (extra rows or zero columns).
- Code: named, opposite 0
- Quote: "iterates through all possible rows regardless of the `rows` variable (which likely tracked the rank or
  successful pivots)" / "prevents the function from slicing away columns that the algorithm deemed
  "unnecessary" or "zeroed out""

**Case 31** `sympy__sympy-24066|gemma-4-31b|a1eb1d06`
- Main defect: the patch hard-codes `Dimension(1)` for every Function, so it ignores the argument dimensions and
  the errors they should raise.
- Code: named, opposite 0
- Quote: "While this is a broad stroke (it assumes *all* `sympy.Function` objects are dimensionless)"
