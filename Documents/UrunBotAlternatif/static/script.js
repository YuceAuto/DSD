// ----------------------------------------------------
// script.js (Gerçek zamanlı "stream" yanıt almak için düzenlendi)
// ----------------------------------------------------

// 1) Kalıcı user_id sakla
function getOrCreateUserId() {
  let existing = localStorage.getItem("skodaBotUserId");
  if (existing) {
    return existing;
  }
  // Yeni ID:
  let newId;
  if (window.crypto && crypto.randomUUID) {
    newId = crypto.randomUUID();
  } else {
    // Fallback random
    newId = 'xxxx-4xxx-yxxx-xxxx'.replace(/[xy]/g, function (c) {
      let r = Math.random() * 16 | 0;
      let v = (c === 'x') ? r : (r & 0x3 | 0x8);
      return v.toString(16);
    });
  }
  localStorage.setItem("skodaBotUserId", newId);
  return newId;
}

// 2) Modal büyük görsel gösterme
function showPopupImage(imgUrl) {
  $("#popupImage").attr("src", imgUrl);
}

// Basit tablo dönüştürme
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

// Metni tablo/normal parçalara bölme (basit)
function splitNonTableTextIntoBubbles(fullText) {
  // İsterseniz daha akıllı bir parçalayıcı yapabilirsiniz.
  // Burada sadece tek bir parça dönüyoruz.
  return [ fullText ];
}

// Gelen bot mesajını baloncuklar olarak ekrana basma
function processBotMessage(fullText, uniqueId) {
  // "Yazıyor..." placeholder'ını kaldıralım
  $(`#botMessageContent-${uniqueId}`).closest(".d-flex").remove();

  // Tabloları bulmak için regex
  let normalizedText = fullText
    .replace(/\\n/g, "\n")
    .replace(/<br\s*\/?>/gi, "\n");

  // CONVERSATION_ID yakala
  let conversationId = null;
  const convMatch = normalizedText.match(/\[CONVERSATION_ID=(\d+)\]/);
  if (convMatch) {
    conversationId = convMatch[1];
    normalizedText = normalizedText.replace(convMatch[0], "");
  }

  const tableRegexGlobal = /(\|.*?\|\n\|.*?\|\n[\s\S]+?)(?=\n\n|$)/g;
  let newBubbles = [];
  let lastIndex = 0;
  let match;

  while ((match = tableRegexGlobal.exec(normalizedText)) !== null) {
    const tableMarkdown = match[1];
    const textBefore = normalizedText.substring(lastIndex, match.index).trim();
    if (textBefore) {
      let splitted = splitNonTableTextIntoBubbles(textBefore);
      splitted.forEach(sub => newBubbles.push({ type: 'text', content: sub }));
    }
    newBubbles.push({ type: 'table', content: tableMarkdown });
    lastIndex = tableRegexGlobal.lastIndex;
  }
  // Son kısım
  if (lastIndex < normalizedText.length) {
    const textAfter = normalizedText.substring(lastIndex).trim();
    if (textAfter) {
      let splitted = splitNonTableTextIntoBubbles(textAfter);
      splitted.forEach(sub => newBubbles.push({ type: 'text', content: sub }));
    }
  }

  // Her bubble ayrı balon olarak ekleyelim
  newBubbles.forEach((bubble, index) => {
    const bubbleId = "separateBubble_" + Date.now() + "_" + Math.random();
    const currentTime = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    let bubbleContent = "";
    if (bubble.type === "table") {
      bubbleContent = markdownTableToHTML(bubble.content);
    } else {
      bubbleContent = bubble.content.replace(/\n/g, "<br>");
    }

    // Beğen butonunu sadece son bubble'a ekliyoruz (opsiyonel)
    const isLastBubble = (index === newBubbles.length - 1);
    let likeButtonHtml = "";
    if (isLastBubble && conversationId) {
      likeButtonHtml = `
        <button class="like-button" data-conversation-id="${conversationId}">
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

  // Form submit
  $("#messageArea").on("submit", function (e) {
    e.preventDefault();
    const inputField = $("#text");
    let rawText = inputField.val().trim();
    if (!rawText) return;

    const currentTime = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    // Kullanıcı mesaj balonu
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

    // Bot "yazıyor" placeholder
    const uniqueId = Date.now();
    const botHtml = `
      <div class="d-flex justify-content-start mb-4">
        <img src="static/images/fotograf.png"
             class="rounded-circle user_img_msg"
             alt="bot image">
        <div class="msg_cotainer">
          <span id="botMessageContent-${uniqueId}">Yazıyor...</span>
        </div>
        <span class="msg_time">${currentTime}</span>
      </div>
    `;
    $("#messageFormeight").append(botHtml);
    $("#messageFormeight").scrollTop($("#messageFormeight")[0].scrollHeight);

    // Artık stream ile okuma:
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
      return response.body; // <-- body: ReadableStream
    })
    .then(stream => {
      // stream'i parça parça okuyacağız
      const reader = stream.getReader();
      const decoder = new TextDecoder("utf-8");
      let partialText = "";

      function readChunk() {
        return reader.read().then(({ done, value }) => {
          if (done) {
            // Stream tamamlandı
            // Tüm metni tablo vs. ayrıştırmak için processBotMessage'a gönderelim
            processBotMessage(partialText, uniqueId);
            return;
          }
          // Akış devam
          const chunkStr = decoder.decode(value, { stream: true });
          partialText += chunkStr;

          // İsterseniz her chunk geldiğinde placeholder'a ekleyebilirsiniz:
          // $("#botMessageContent-"+uniqueId).append(document.createTextNode(chunkStr));
          // Veya alt satır:
          document.getElementById(`botMessageContent-${uniqueId}`).textContent += chunkStr;

          $("#messageFormeight").scrollTop($("#messageFormeight")[0].scrollHeight);

          return readChunk(); // döngü
        });
      }
      return readChunk();
    })
    .catch(err => {
      console.error("Hata:", err);
      $(`#botMessageContent-${uniqueId}`).text("Bir hata oluştu: " + err.message);
    });

    // Oturum bildirimi örneği (9 dakika sonra)
    setTimeout(() => {
      const barEl = document.getElementById('notificationBar');
      if (barEl) {
        barEl.style.display = 'block';
      }
    }, 9 * 60 * 1000);
  });
});

// "Beğen" butonu
$(document).on("click", ".like-button", function() {
  const $btn = $(this);
  if ($btn.hasClass("clicked")) {
    // Geri al
    $btn.removeClass("clicked");
    $btn.text("Beğen");
  } else {
    // ilk kez beğen
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
