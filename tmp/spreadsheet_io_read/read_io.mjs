import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const source = "C:/Users/Administrator/Desktop/ITRI/MVP_Ramen/0.Old/2_IO/SS101B拉麵機訊號串接規劃.xlsx";
const input = await FileBlob.load(source);
const workbook = await SpreadsheetFile.importXlsx(input);

const sheets = await workbook.inspect({
  kind: "sheet",
  include: "id,name",
  maxChars: 6000,
});
console.log("SHEETS");
console.log(sheets.ndjson);

for (const term of ["EMC", "X0.", "急停", "緊急", "安全", "Robot", "Nachi"]) {
  const matches = await workbook.inspect({
    kind: "match",
    searchTerm: term,
    options: { useRegex: false, maxResults: 100 },
    maxChars: 12000,
  });
  console.log(`MATCH ${term}`);
  console.log(matches.ndjson);
}

for (const [sheetId, range] of [
  ["與KS交握訊號", "A1:H41"],
  ["Nachi手臂交握訊號", "A1:K54"],
  ["代碼表", "A1:D26"],
]) {
  const region = await workbook.inspect({
    kind: "table",
    sheetId,
    range,
    include: "values,formulas",
    tableMaxRows: 60,
    tableMaxCols: 12,
    tableMaxCellChars: 300,
    maxChars: 30000,
  });
  console.log(`TABLE ${sheetId} ${range}`);
  console.log(region.ndjson);
}
