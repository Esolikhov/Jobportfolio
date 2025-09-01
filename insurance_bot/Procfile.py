"function SendTelegram() {
  const ui = SpreadsheetApp.getUi();
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  let cell = sheet.getActiveCell();
  let name = sheet.getName();
  if (name === "Сводная"  name === "Ежедневная промывка"  name === "Summary" || name === "P&L") return;
  let data = sheet.getRange(cell.getRow(), 1, 1, 18).getDisplayValues()[0];
  let text = `
<b>Отчёт по производству</b>
Лист: <b>${name}</b>
⠀
Дата: <b>${data[1]}</b>
Блок: <b>${data[2]}</b>
Время работы: <b>${data[5]}</b>
⠀
Объем промывки (м3): <b>${data[9]}</b> м3
Объем промывки (м3/ч): <b>${data[11]}</b> м3/ч
Шл. Золота (гр): <b>${data[13]}</b> гр
Средние содержание шл. золота (мг/m³): <b>${data[15]}</b> мг/m³
`
   if (cell.getColumn() === 14 && cell.getValue() !== '')
   { sendText("-1001937684855", text) }
}

function sendText(chatId, text) {
  UrlFetchApp.fetch(https://api.telegram.org/bot"7781016119:AAHbNwdcGvsV-JcrffQPY8g753hRwfxm44I"/sendMessage, {
    method: 'post',
    payload: {
      chat_id: String(chatId),
      text: text,
      parse_mode: 'HTML'
    }
  })
}"