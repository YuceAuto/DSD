// ----------------------------------------------------
// script.js (Gerçek zamanlı stream + tablo işleme)
// + Local Storage user_id
// + Görsel popup fonksiyonu
// + Son baloncukta "Beğen" butonu
// + "Beğen" POST isteği
// ----------------------------------------------------

// 1) Tarayıcıda kalıcı (localStorage) benzersiz kullanıcı ID oluşturma
function getOrCreateUserId() {
  let existing = localStorage.getItem("skodaBotUserId");
  if (existing) {
    return existing;
  }
  // Yeni bir UUID üret
  let newId;
  if (window.crypto && crypto.randomUUID) {
    newId = crypto.randomUUID();
  } else {
    newId = 'xxxx-4xxx-yxxx-xxxx'.replace(/[xy]/g, function (c) {
      let r = Math.random() * 16 | 0;
      let v = c === 'x' ? r : (r & 0x3 | 0x8);
      return v.toString(16);
    });
  }
  localStorage.setItem("skodaBotUserId", newId);
  return newId;
}

// 2) Görsele tıklanınca modal içinde açmayı sağlayan fonksiyon
function showPopupImage(imgUrl) {
  $("#popupImage").attr("src", imgUrl);
}

// Belirli özel pattern'leri yakalamak için örnek fonksiyon
function extractTextContentBlock(fullText) {
  const regex = /\[TextContentBlock\(.*?value=(['"])([\s\S]*?)\1.*?\)\]/;
  const match = regex.exec(fullText);
  if (match && match[2]) {
    return match[2];
  }
  return null;
}

// Basit bir Markdown tablo -> HTML dönüşüm örneği
function markdownTableToHTML(mdTable) {
  const lines = mdTable.trim().split("\n").map(line => line.trim());
  if (lines.length < 2) {
    return `<p>${mdTable}</p>`;
  }
  const headerLine = lines[0];
  const headerCells = headerLine.split("|").map(cell => cell.trim()).filter(Boolean);
  const bodyLines = lines.slice(2);

  let html = `<table class="table table-bordered table-sm my-blue-table">
                <thead>
                  <tr>`;

  headerCells.forEach(cell => {
    html += `<th>${cell}</th>`;
  });
  html += `   </tr>
            </thead>
            <tbody>
  `;

  bodyLines.forEach(line => {
    if (!line.trim()) return;
    const cols = line.split("|").map(col => col.trim()).filter(Boolean);
    if (cols.length === 0) return;
    html += `<tr>`;
    cols.forEach(col => {
      html += `<td>${col}</td>`;
    });
    html += `</tr>`;
  });
  html += `
            </tbody>
          </table>`;
  return html;
}

// Metni, tablolar vs. yoksa normal şekilde parçalara bölmek
function splitNonTableTextIntoBubbles(fullText) {
  const trimmedText = fullText.trim();
  const lines = trimmedText.split(/\r?\n/);

  // Örnek ayrıştırma mantığı:
  let firstColonIndex = -1;
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].trim().match(/:$/)) {
      firstColonIndex = i;
      break;
    }
  }

  function findMoreInfoLineIndex(startIndex, arr) {
    for (let i = startIndex; i < arr.length; i++) {
      if (arr[i].toLowerCase().includes("daha fazla bilgi almak istediğiniz")) {
        return i;
      }
    }
    return -1;
  }

  let resultBubbles = [];
  if (firstColonIndex !== -1) {
    const bubble1 = lines[firstColonIndex].trim();
    resultBubbles.push(bubble1);

    const restLines = lines.slice(firstColonIndex + 1);
    const moreInfoIndex = findMoreInfoLineIndex(0, restLines);
    if (moreInfoIndex !== -1) {
      const bubble2 = restLines.slice(0, moreInfoIndex).join("\n").trim();
      if (bubble2) {
        resultBubbles.push(bubble2);
      }
      const bubble3 = restLines[moreInfoIndex].trim();
      resultBubbles.push(bubble3);
      if (moreInfoIndex + 1 < restLines.length) {
        const bubble4 = restLines.slice(moreInfoIndex + 1).join("\n").trim();
        if (bubble4) {
          resultBubbles.push(bubble4);
        }
      }
    } else {
      const bubble2 = restLines.join("\n").trim();
      if (bubble2) {
        resultBubbles.push(bubble2);
      }
    }
  } else {
    const moreInfoIndex = findMoreInfoLineIndex(0, lines);
    if (moreInfoIndex !== -1) {
      const bubble1 = lines.slice(0, moreInfoIndex).join("\n").trim();
      if (bubble1) {
        resultBubbles.push(bubble1);
      }
      resultBubbles.push(lines[moreInfoIndex].trim());
      if (moreInfoIndex + 1 < lines.length) {
        const bubble3 = lines.slice(moreInfoIndex + 1).join("\n").trim();
        if (bubble3) {
          resultBubbles.push(bubble3);
        }
      }
    } else {
      resultBubbles.push(trimmedText);
    }
  }
  return resultBubbles;
}

/**
 * Bot mesajını işleyip, tablo varsa tabloyu HTML'e çevirip,
 * yoksa normal text olarak birden fazla baloncuk üreterek ekrana basar.
 */
function processBotMessage(fullText, uniqueId) {
  // Bot'tan gelen ham text'i normalleştir
  let normalizedText = fullText
    .replace(/\\n/g, "\n")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/[–—]/g, '-');

  // Özel pattern "[CONVERSATION_ID=xxx]" yakala
  let conversationId = null;
  const matchConv = normalizedText.match(/\[CONVERSATION_ID=(\d+)\]/);
  if (matchConv) {
    conversationId = matchConv[1];
    // metinden çıkaralım ki baloncukta görünmesin
    normalizedText = normalizedText.replace(matchConv[0], "");
  }

  // Bazı özel pattern'leri ayıklama (opsiyonel)
  const extractedValue = extractTextContentBlock(normalizedText);
  const textToCheck = extractedValue ? extractedValue : normalizedText;

  // Tablo regex
  const tableRegexGlobal = /(\|.*?\|\n\|.*?\|\n[\s\S]+?)(?=\n\n|$)/g;
  let newBubbles = [];
  let lastIndex = 0;
  let match;

  // Tabloları yakala ve parçala
  while ((match = tableRegexGlobal.exec(textToCheck)) !== null) {
    const tableMarkdown = match[1];
    const textBefore = textToCheck.substring(lastIndex, match.index).trim();
    if (textBefore) {
      const splittedTextBubbles = splitNonTableTextIntoBubbles(textBefore);
      splittedTextBubbles.forEach(subPart => {
        newBubbles.push({ type: 'text', content: subPart });
      });
    }
    newBubbles.push({ type: 'table', content: tableMarkdown });
    lastIndex = tableRegexGlobal.lastIndex;
  }

  // Son tablodan sonraki metin
  if (lastIndex < textToCheck.length) {
    const textAfter = textToCheck.substring(lastIndex).trim();
    if (textAfter) {
      const splittedTextBubbles = splitNonTableTextIntoBubbles(textAfter);
      splittedTextBubbles.forEach(subPart => {
        newBubbles.push({ type: 'text', content: subPart });
      });
    }
  }

  // Bot "typing" placeholder'ını (id=botMessageContent-uniqueId) kaldıralım
  $(`#botMessageContent-${uniqueId}`).closest(".d-flex").remove();

  // Her bubble'ı ayrı mesaj balonu yaparak ekrana bas
  newBubbles.forEach((bubble, index) => {
    const bubbleId = "separateBubble_" + Date.now() + "_" + Math.random();
    const currentTime = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    let bubbleContent = "";
    if (bubble.type === "table") {
      bubbleContent = markdownTableToHTML(bubble.content);
    } else {
      // normal text
      bubbleContent = bubble.content.replace(/\n/g, "<br>");
    }

    // Sadece son baloncukta "Beğen" butonu
    const isLastBubble = (index === newBubbles.length - 1);
    let likeButtonHtml = "";
    if (isLastBubble && conversationId) {
      likeButtonHtml = `
        <button class="like-button"
                style="margin-top:6px;"
                data-conversation-id="${conversationId}">
          Beğen
        </button>
      `;
    }

    const botHtml = `
      <div class="d-flex justify-content-start mb-4">
        <img src="static/images/fotograf.png"
             class="rounded-circle user_img_msg"
             alt="bot image">
        <div class="msg_cotainer">
          <span id="botMessageContent-${bubbleId}">${bubbleContent}</span>
          ${likeButtonHtml}
        </div>
        <span class="msg_time">${currentTime}</span>
      </div>
    `;

    $("#messageFormeight").append(botHtml);
    $("#messageFormeight").scrollTop($("#messageFormeight")[0].scrollHeight);
  });
}

$(document).ready(function () {
  const localUserId = getOrCreateUserId();

  $("#messageArea").on("submit", function (e) {
    e.preventDefault();
    const inputField = $("#text");
    let rawText = inputField.val().trim();
    if (!rawText) return;

    const currentTime = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    // Kullanıcının mesaj balonu
    const userHtml = `
      <div class="d-flex justify-content-end mb-4">
        <div class="msg_cotainer_send">
          ${rawText}
          <span class="msg_time_send">${currentTime}</span>
        </div>
        <img src="static/images/fotograf.png"
             class="rounded-circle user_img_msg"
             alt="user image">
      </div>
    `;
    $("#messageFormeight").append(userHtml);
    inputField.val("");

    // Botun "yazıyor" placeholder'ı
    const uniqueId = Date.now();
    const botHtml = `
      <div class="d-flex justify-content-start mb-4">
        <img src="static/images/fotograf.png"
             class="rounded-circle user_img_msg"
             alt="bot image">
        <div class="msg_cotainer">
          <span id="botMessageContent-${uniqueId}"></span>
        </div>
        <span class="msg_time">${currentTime}</span>
      </div>
    `;
    $("#messageFormeight").append(botHtml);
    $("#messageFormeight").scrollTop($("#messageFormeight")[0].scrollHeight);

    // /ask endpointine POST (stream)
    fetch("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: rawText,
        user_id: localUserId
      })
    })
      .then(response => {
        if (!response.ok) {
          throw new Error("Sunucu hatası: " + response.status);
        }
        return response.body;
      })
      .then(stream => {
        const reader = stream.getReader();
        const decoder = new TextDecoder("utf-8");
        let partialText = "";

        function readChunk() {
          return reader.read().then(({ done, value }) => {
            if (done) {
              // AKIŞ TAMAMLANDI
              // 1) "yazıyor" placeholder'ını temizle
              $(`#botMessageContent-${uniqueId}`).html("");
              // 2) Tam metni tablo vb. işleme sok
              processBotMessage(partialText, uniqueId);
              return;
            }
            // AKIŞ DEVAM EDİYOR
            const chunkText = decoder.decode(value, { stream: true });
            partialText += chunkText;

            // Gelen parçayı ekranda göster
            $(`#botMessageContent-${uniqueId}`).html(
              partialText.replace(/\n/g, "<br>")
            );

            $("#messageFormeight").scrollTop($("#messageFormeight")[0].scrollHeight);
            return readChunk();
          });
        }
        return readChunk();
      })
      .catch(err => {
        console.error("Hata:", err);
        $(`#botMessageContent-${uniqueId}`).text("Bir hata oluştu: " + err.message);
      });

    // 9 dakika sonra bildirim çubuğu gösterme (örnek)
    setTimeout(() => {
      const barEl = document.getElementById('notificationBar');
      if (barEl) {
        barEl.style.display = 'block';
      }
    }, 9 * 60 * 1000);
  });
});

// "Beğen" butonuna tıklama olayı
$(document).on("click", ".like-button", function(event) {
  event.preventDefault();
  const $btn = $(this);
  if ($btn.hasClass("clicked")) {
    // Beğeniyi geri alma örneği (opsiyonel)
    $btn.removeClass("clicked");
    $btn.text("Beğen");
    // Geri almayı DB'ye kaydetmek istersen /unlike vs. gönderebilirsin.
  } else {
    // İlk kez beğen
    $btn.addClass("clicked");
    $btn.text("Beğenildi");

    const convId = $btn.data("conversation-id");
    if (convId) {
      fetch("/like", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ conversation_id: convId })
      })
      .then(res => res.json())
      .then(data => {
        if (data.status === "ok") {
          console.log("Veritabanı güncellendi: customer_answer=1");
        } else {
          console.log("Like güncelleme hatası:", data);
        }
      })
      .catch(err => console.error("Like POST hatası:", err));
    }
  }
});