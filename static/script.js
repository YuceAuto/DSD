// ----------------------------------------------------
// script.js (Şeffaf, Font Awesome ikonlu Like / Dislike)
// + Yalnızca ikon rengi değişsin (arka plan yok)
// + Bir buton tıklanınca diğerini pasif yap
// ----------------------------------------------------

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

function showPopupImage(imgUrl, size = 'normal') {
  $("#popupImage").attr("src", imgUrl);
  if (size === 'smaller') {
    $("#popupImage").addClass("popupImageSmaller");
  } else {
    $("#popupImage").removeClass("popupImageSmaller");
  }
}

function extractTextContentBlock(fullText) {
  const regex = /\[TextContentBlock\(.*?value=(['"])([\s\S]*?)\1.*?\)\]/;
  const match = regex.exec(fullText);
  if (match && match[2]) {
    return match[2];
  }
  return null;
}

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
  html +=    `</tr>
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

function splitNonTableTextIntoBubbles(fullText) {
  const trimmedText = fullText.trim();
  const lines = trimmedText.split(/\r?\n/);

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
 * Botun cevabını parça parça işleyip, 
 * her parça için ortada (baloncuksuz) gösteriyoruz.
 */
function processBotMessage(fullText, uniqueId) {
  // Bot'tan gelen ham text'i normalleştir
  let normalizedText = fullText
    .replace(/\\n/g, "\n")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/[–—]/g, '-');

  // "[CONVERSATION_ID=xxx]" yakala
  let conversationId = null;
  const matchConv = normalizedText.match(/\[CONVERSATION_ID=(\d+)\]/);
  if (matchConv) {
    conversationId = matchConv[1];
    normalizedText = normalizedText.replace(matchConv[0], "");
  }

  const extractedValue = extractTextContentBlock(normalizedText);
  const textToCheck = extractedValue ? extractedValue : normalizedText;

  // Tablo regex
  const tableRegexGlobal = /(\|.*?\|\n\|.*?\|\n[\s\S]+?)(?=\n\n|$)/g;
  let newBubbles = [];
  let lastIndex = 0;
  let match;

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

  if (lastIndex < textToCheck.length) {
    const textAfter = textToCheck.substring(lastIndex).trim();
    if (textAfter) {
      const splittedTextBubbles = splitNonTableTextIntoBubbles(textAfter);
      splittedTextBubbles.forEach(subPart => {
        newBubbles.push({ type: 'text', content: subPart });
      });
    }
  }

  // "yazıyor" placeholder'ını kaldır
  $(`#botMessageContent-${uniqueId}`).closest(".d-flex").remove();

  newBubbles.forEach((bubble, index) => {
    const bubbleId = "separateBubble_" + Date.now() + "_" + Math.random();
    let bubbleContent = "";

    if (bubble.type === "table") {
      bubbleContent = markdownTableToHTML(bubble.content);
    } else {
      bubbleContent = bubble.content.replace(/\n/g, "<br>");
    }

    // Sadece son bubble'da like/dislike butonlarını göster
    const isLastBubble = (index === newBubbles.length - 1);
    let likeButtonHtml = "";
    // conversationId Yakalandıysa buton ekle
    if (isLastBubble && conversationId) {
      // Font Awesome ikonlu butonlar
      likeButtonHtml = `
        <button class="like-button" data-conversation-id="${conversationId}">
          <i class="fa-solid fa-thumbs-up" style="color: #f2f2f2;"></i>
        </button>
        <button class="dislike-button" data-conversation-id="${conversationId}">
          <i class="fa-solid fa-thumbs-down" style="color: #f2f2f2;"></i>
        </button>
      `;
    }

    const botHtml = `
      <div class="d-flex justify-content-center mb-4 w-100">
        <div class="assistant_message_container">
          <span id="botMessageContent-${bubbleId}">${bubbleContent}</span>
          ${likeButtonHtml}
        </div>
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
    // Kullanıcı mesajı
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

    // Bot "yazıyor..." placeholder
    const uniqueId = Date.now();
    const botHtml = `
      <div class="d-flex justify-content-start mb-4">
        <img src="static/images/fotograf.png"
             class="rounded-circle user_img_msg"
             alt="bot image">
        <div class="msg_cotainer" id="botMessageContent-${uniqueId}">
          Yazıyor...
        </div>
      </div>
    `;
    $("#messageFormeight").append(botHtml);
    $("#messageFormeight").scrollTop($("#messageFormeight")[0].scrollHeight);

    // /ask endpoint
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
        let botMessage = "";

        function readChunk() {
          return reader.read().then(({ done, value }) => {
            if (done) {
              processBotMessage(botMessage, uniqueId);
              return;
            }
            const chunkText = decoder.decode(value, { stream: true });
            botMessage += chunkText;
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
  });
});

// -----------------------------------------------------
// LIKE BUTONU TIKLANINCA
// -----------------------------------------------------
$(document).on("click", ".like-button", function(event) {
  event.preventDefault();
  const $likeBtn = $(this);
  const $dislikeBtn = $(".dislike-button"); // diğer butonu

  // Diğer butonun .clicked sınıfını kaldır
  $dislikeBtn.removeClass("clicked");

  // Toggle
  if ($likeBtn.hasClass("clicked")) {
    // Zaten tıklı -> unclick
    $likeBtn.removeClass("clicked");
  } else {
    // Yeni tıklama
    $likeBtn.addClass("clicked");

    const convId = $likeBtn.data("conversation-id");
    if (convId) {
      fetch("/like", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ conversation_id: convId })
      })
      .then(res => res.json())
      .then(data => {
        console.log("Like POST yanıtı:", data);
      })
      .catch(err => console.error("Like POST hatası:", err));
    }
  }
});

// -----------------------------------------------------
// DISLIKE BUTONU TIKLANINCA
// -----------------------------------------------------
$(document).on("click", ".dislike-button", function(event) {
  event.preventDefault();
  const $dislikeBtn = $(this);
  const $likeBtn = $(".like-button");

  // Diğer butonun .clicked sınıfını kaldır
  $likeBtn.removeClass("clicked");

  // Toggle
  if ($dislikeBtn.hasClass("clicked")) {
    $dislikeBtn.removeClass("clicked");
  } else {
    $dislikeBtn.addClass("clicked");

    const convId = $dislikeBtn.data("conversation-id");
    if (convId) {
      fetch("/dislike", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ conversation_id: convId })
      })
      .then(res => res.json())
      .then(data => {
        console.log("Dislike POST yanıtı:", data);
      })
      .catch(err => console.error("Dislike POST hatası:", err));
    }
  }
});

/**
 * ==============================
 *  EKLENEN SENDMESSAGE FONKSİYONU
 * ==============================
 */
function sendMessage(textToSend) {
  const inputField = $("#text");
  inputField.val(textToSend);
  $("#messageArea").submit();
}