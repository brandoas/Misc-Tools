Write a Python script that cleans up a PowerPoint (.pptx) file by doing the following two things:

1. Remove all slide-level background overrides
For every slide in the presentation, remove the <p:bg> element from the slide XML (ppt/slides/slideN.xml) so that all slides revert to inheriting their background from the slide master/layout. Do NOT touch the slide master or layout backgrounds — only remove overrides at the individual slide level.

The <p:bg> element is a direct child of <p:cSld> in each slide XML file.

2. Remove trailing empty paragraphs and trailing line breaks from all text shapes
For every <a:txBody> in every slide:

Remove trailing empty <a:p> elements (paragraphs that contain no <a:r> text runs — only <a:pPr> and/or <a:endParaRPr>). Always keep at least one <a:p> per text body.
Within each remaining <a:p>, remove any trailing <a:br> (line break) elements that appear before the final <a:endParaRPr>.
These empty paragraphs and trailing line breaks create unwanted blank lines/spaces after bullet points.

Requirements:
Use python-pptx for accessing the PPTX zip structure, or just use zipfile + lxml.etree directly for XML manipulation.
Accept an input file path and output file path as command-line arguments.
Preserve all images, charts, tables, and other non-text content untouched.
Use proper XML namespace handling for the PowerPoint OOXML namespaces:
p = http://schemas.openxmlformats.org/presentationml/2006/main
a = http://schemas.openxmlformats.org/drawingml/2006/main
Print a summary of what was changed (e.g., "Removed background override from slide 5", "Removed 3 empty trailing paragraphs from slide 12").