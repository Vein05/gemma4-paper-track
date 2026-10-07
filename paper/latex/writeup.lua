-- Pandoc filter: turn the Kaggle-ready writeup.md into the preprint layout.
-- H1 -> title; "**Subtitle.** ..." -> italic line under the title; "## Abstract" section -> abstract;
-- PNG figures (Kaggle) -> PDF figures (print, figures/pdf/); "**Figure N.** ..." paragraph -> that figure's caption;
-- HTML comments dropped.
local stringify = pandoc.utils.stringify

function Pandoc(doc)
  local blocks, meta = doc.blocks, doc.meta
  local out, abstract, in_abstract = {}, {}, false
  local i = 1
  while i <= #blocks do
    local b = blocks[i]
    if b.t == "Header" and b.level == 1 then
      meta.title = pandoc.MetaInlines(b.content)
    elseif b.t == "Para" and b.content[1] and b.content[1].t == "Strong" and stringify(b.content[1]) == "Subtitle." then
      local rest = pandoc.List({table.unpack(b.content, 3)})
      local t = pandoc.List(meta.title)
      t:insert(pandoc.RawInline("latex", "\\\\[0.8em]{\\normalfont\\normalsize\\itshape "))
      t:extend(rest)
      t:insert(pandoc.RawInline("latex", "\\par}"))
      meta.title = pandoc.MetaInlines(t)
    elseif b.t == "Header" and b.level == 2 and stringify(b.content) == "Abstract" then
      in_abstract = true
    elseif in_abstract and b.t ~= "Header" then
      table.insert(abstract, b)
    elseif b.t == "RawBlock" and b.format == "html" then
      -- drop comments
    else
      if b.t == "Header" then in_abstract = false end
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

-- Tables: pandoc writes breakable longtables; short tables read better kept whole, so emit a tabular in a [H] float.
function Table(tbl)
  local tex = pandoc.write(pandoc.Pandoc({tbl}), "latex")
  tex = tex:gsub("\\begin{longtable}%[%]", "\\begin{table}[H]\\centering\\small\\begin{tabular}")
  tex = tex:gsub("\\end{longtable}", "\\end{tabular}\\end{table}")
  for _, cmd in ipairs({"\\endfirsthead", "\\endhead", "\\endfoot", "\\endlastfoot"}) do
    tex = tex:gsub(cmd, "")
  end
  return pandoc.RawBlock("latex", tex)
end
