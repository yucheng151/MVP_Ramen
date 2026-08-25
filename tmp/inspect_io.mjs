import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const input = await FileBlob.load("4.IO/MVP_Ramen_Comm_IO_Table_v3.xlsx");
const workbook = await SpreadsheetFile.importXlsx(input);
const result = await workbook.inspect({
  kind: "workbook,sheet,table,region",
  maxChars: 50000,
  tableMaxRows: 80,
  tableMaxCols: 20,
  tableMaxCellChars: 160,
});
process.stdout.write(result.ndjson);
