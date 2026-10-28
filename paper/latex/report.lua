-- Pandoc filter: writeup.md -> the report layout (latex/report-template.tex).
-- H1 -> title; "**Subtitle.** ..." -> subtitle; "## Abstract" section -> abstract; numbered headings -> \rsection /
-- \rsubsection; PNG figures -> print PDFs (figures/pdf/); "**Figure N.** ..." paragraph -> caption;
-- tables -> booktabs tabulars in an rtable environment; HTML comments dropped.
local stringify = pandoc.utils.stringify

local function latex_inlines(inl)
  return (pandoc.write(pandoc.Pandoc({pandoc.Plain(inl)}), "latex", {wrap_text = "none"}):gsub("%s+$", ""))
end

local function heading(b, before_figure)
  local text = latex_inlines(b.content)
  local num, rest = text:match("^([%d%.]+)%s+(.*)$")
  if not num then num, rest = "", text end
  num = num:gsub("%.$", "")
  -- keep a heading with what follows; a heading right before a figure needs room for the figure too
  local need = before_figure and "\\Needspace{0.5\\textheight}" or "\\Needspace{6\\baselineskip}"
  if b.level == 2 then
    return pandoc.RawBlock("latex", need .. string.format("\\rsection{%s}{%s}", num, rest))
  end
  return pandoc.RawBlock("latex", need .. string.format("\\rsubsection{%s}{%s}", num, rest))
end

local function cell(c)
  return (pandoc.write(pandoc.Pandoc(c.contents), "latex", {wrap_text = "none"}):gsub("\n", " "):gsub("%s+$", ""))
end

-- Tables: first column left, others centred; widths from the Markdown dash counts; Gemma's own row tinted.
local function table_tex(tbl)
  local n = #tbl.colspecs
  local widths, total = {}, 0
  for i, cs in ipairs(tbl.colspecs) do
    local w = cs[2]
    if type(w) ~= "number" or w ~= w then w = 1 / n end
    widths[i] = w; total = total + w
  end
  local spec = {}
  for i = 1, n do
    local w = string.format("\\dimexpr(\\linewidth-%d\\tabcolsep)*%d/1000\\relax", 2 * n, math.floor(1000 * widths[i] / total))
    spec[i] = (i == 1 and "L{" or "C{") .. w .. "}"
  end
  local out = {"\\begin{rtable}", "\\begin{tabular}{" .. table.concat(spec) .. "}", "\\toprule"}
  for _, row in ipairs(tbl.head.rows) do
    local cells = {}
    for _, c in ipairs(row.cells) do table.insert(cells, "\\textbf{" .. cell(c) .. "}") end
    table.insert(out, "\\rowcolor{headbg}" .. table.concat(cells, " & ") .. " \\\\")
  end
  table.insert(out, "\\midrule")
  for _, body in ipairs(tbl.bodies) do
    for _, row in ipairs(body.body) do
      local cells = {}
      for _, c in ipairs(row.cells) do table.insert(cells, cell(c)) end
      local tint = (cells[1]:match("^Gemma's own") or cells[1]:match("^Gemma 4")) and "\\rowcolor{gemmasoft}" or ""
      table.insert(out, tint .. table.concat(cells, " & ") .. " \\\\")
    end
  end
  table.insert(out, "\\bottomrule")
  table.insert(out, "\\end{tabular}")
  table.insert(out, "\\end{rtable}")
  return pandoc.RawBlock("latex", table.concat(out, "\n"))
end

function Pandoc(doc)
  local blocks, meta = doc.blocks, doc.meta
  local out, abstract, in_abstract = {}, {}, false
  local i = 1
  while i <= #blocks do
    local b = blocks[i]
    if b.t == "Header" and b.level == 1 then
      meta.title = pandoc.MetaInlines(b.content)
    elseif b.t == "Para" and b.content[1] and b.content[1].t == "Strong" and stringify(b.content[1]) == "Subtitle." then
      meta.subtitle = pandoc.MetaInlines(pandoc.List({table.unpack(b.content, 3)}))
    elseif b.t == "Header" and b.level == 2 and stringify(b.content) == "Abstract" then
      in_abstract = true
    elseif in_abstract and b.t ~= "Header" then
      table.insert(abstract, b)
    elseif b.t == "RawBlock" and b.format == "html" then
      -- drop comments
    elseif b.t == "Header" then
      in_abstract = false
      table.insert(out, heading(b, blocks[i + 1] and blocks[i + 1].t == "Figure"))
    elseif b.t == "Table" then
      table.insert(out, table_tex(b))
    else
      if b.t == "Figure" and blocks[i + 1] and blocks[i + 1].t == "Para" then
        local nxt = blocks[i + 1].content
        if nxt[1] and nxt[1].t == "Strong" and stringify(nxt[1]):match("^Figure %d+%.$") then
          b.caption = pandoc.Caption({pandoc.Plain(pandoc.List({table.unpack(nxt, 3)}))})
          i = i + 1
        end
      end
      table.insert(out, b)
    end
    i = i + 1
  end
  meta.abstract = pandoc.MetaBlocks(abstract)
  return pandoc.Pandoc(out, meta)
end

function Image(img)
  img.src = img.src:gsub("^figures/(.-)%.png$", "figures/pdf/%1.pdf")
  img.attributes.width = "100%"
  return img
end
