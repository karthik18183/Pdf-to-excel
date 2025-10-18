help:
	@echo "Targets:"
	@echo "  run PDF=/path/file.pdf OUT=/path/out.xlsx [TEMPLATE=config/example_template.yaml]"
	@echo
	@echo "Example:"
	@echo "  make run PDF=statement.pdf OUT=statement.xlsx"
	@echo "  make run PDF=statement.pdf OUT=statement.xlsx TEMPLATE=config/example_template.yaml"

run:
	python parse_pdf_to_excel.py --pdf $(PDF) --out $(OUT) $(if $(TEMPLATE),--template $(TEMPLATE),)
