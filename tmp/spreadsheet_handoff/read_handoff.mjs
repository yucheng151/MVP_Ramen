import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath = "C:/Users/Administrator/Desktop/ITRI/MVP_Ramen/0.Old/2_IO/SS101B拉麵機訊號串接規劃.xlsx";
const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);

const sheets = await workbook.inspect({
  kind: "sheet",
  include: "id,name",
  maxChars: 12000,
});
console.log("=== SHEETS ===");
console.log(sheets.ndjson);

for (const term of [
  "Nashi",
  "Robot",
  "Stand",
  "Idle",
  "手臂",
  "甩麵",
  "倒麵",
  "完成",
  "Command",
  "Finish",
]) {
  const result = await workbook.inspect({
    kind: "match",
    searchTerm: term,
    options: { useRegex: false, maxResults: 100 },
    maxChars: 20000,
  });
  console.log(`=== MATCH ${term} ===`);
  console.log(result.ndjson);
}

for (const [sheetId, range] of [
  ["Nachi手臂交握訊號", "A1:K54"],
  ["代碼表", "A1:D26"],
  ["與KS交握訊號", "A1:H41"],
]) {
  const table = await workbook.inspect({
    kind: "table",
    sheetId,
    range,
    include: "values,formulas",
    tableMaxRows: 60,
    tableMaxCols: 12,
    tableMaxCellChars: 500,
    maxChars: 60000,
  });
  console.log(`=== TABLE ${sheetId} ${range} ===`);
  console.log(table.ndjson);
}

const preview = await workbook.render({
  sheetName: "Nachi手臂交握訊號",
  range: "A1:K54",
  scale: 1.5,
  format: "png",
});
await fs.writeFile(
  "C:/Users/Administrator/Desktop/ITRI/MVP_Ramen/tmp/spreadsheet_handoff/nachi_handoff.png",
  new Uint8Array(await preview.arrayBuffer()),
);
