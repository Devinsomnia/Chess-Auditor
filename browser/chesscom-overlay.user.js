// ==UserScript==
// @name         chess-auditor capture (chess.com)
// @namespace    chess-auditor
// @version      0.2.0
// @description  Reads the live board on chess.com and pushes the position to the
//               local chess-auditor overlay server for broadcast analysis.
// @match        https://www.chess.com/*
// @match        https://chess.com/*
// @grant        GM_xmlhttpRequest
// @grant        unsafeWindow
// @connect      127.0.0.1
// @connect      localhost
// @run-at       document-idle
// @noframes
// ==/UserScript==

(function () {
  "use strict";

  const ENDPOINT = "http://127.0.0.1:8765/fen";
  const TAG = "[chess-auditor]";
  const PIECE_RE = /^([wb])([pnbrqk])$/;
  const SQUARE_RE = /^square-(\d)(\d)$/;

  let lastSent = "";
  console.log(TAG, "userscript loaded on", location.href);

  // ------------------------------------------------------------------
  // Strategy 1 (preferred): chess.com's own board component exposes a
  // `game` API on the <wc-chess-board> element with getFEN()/getPlayingAs().
  // Exact FEN incl. side-to-move and castling — no guessing.
  // Needs the PAGE element (not the isolated-world wrapper), hence unsafeWindow.
  // ------------------------------------------------------------------
  function readViaGameApi() {
    try {
      const doc = (typeof unsafeWindow !== "undefined" ? unsafeWindow : window).document;
      const el =
        doc.querySelector("wc-chess-board") || doc.querySelector("chess-board");
      if (!el || !el.game || typeof el.game.getFEN !== "function") return null;
      const fen = el.game.getFEN();
      if (!fen || typeof fen !== "string" || fen.split(" ").length < 4) return null;

      let color = null;
      try {
        // 1 = white, 2 = black; 0/undefined when only spectating
        const pa = el.game.getPlayingAs && el.game.getPlayingAs();
        if (pa === 1) color = "white";
        else if (pa === 2) color = "black";
      } catch (e) { /* fall through */ }
      if (!color) color = el.classList.contains("flipped") ? "black" : "white";

      return { fen, color, via: "game-api" };
    } catch (e) {
      console.log(TAG, "game API read failed:", e.message);
      return null;
    }
  }

  // ------------------------------------------------------------------
  // Strategy 2 (fallback): scrape piece elements from the DOM.
  // ------------------------------------------------------------------
  function findBoard() {
    return (
      document.querySelector("wc-chess-board") ||
      document.querySelector("chess-board") ||
      document.querySelector(".board")
    );
  }

  function readViaDom() {
    const boardEl = findBoard();
    if (!boardEl) return null;
    const grid = Array.from({ length: 8 }, () => Array(8).fill(null)); // [rank][file]
    const pieces = boardEl.querySelectorAll(".piece, [class*='piece ']");
    if (!pieces.length) return null;

    let found = 0;
    for (const el of pieces) {
      let code = null, file = null, rank = null;
      for (const cls of el.classList) {
        const pm = PIECE_RE.exec(cls);
        if (pm) code = pm[1] === "w" ? pm[2].toUpperCase() : pm[2];
        const sm = SQUARE_RE.exec(cls);
        if (sm) {
          file = parseInt(sm[1], 10) - 1;
          rank = parseInt(sm[2], 10) - 1;
        }
      }
      if (code && file !== null && rank !== null) { grid[rank][file] = code; found++; }
    }
    if (found < 2 || !hasKings(grid)) return null;

    const bottom = boardEl.classList.contains("flipped") ? "black" : "white";
    const turn = sideToMove(bottom) === "white" ? "w" : "b";
    const fen = `${placementToFen(grid)} ${turn} ${castling(grid)} - 0 1`;
    return { fen, color: bottom, via: "dom" };
  }

  function placementToFen(grid) {
    const rows = [];
    for (let rank = 7; rank >= 0; rank--) {
      let row = "", empty = 0;
      for (let file = 0; file < 8; file++) {
        const p = grid[rank][file];
        if (!p) { empty++; }
        else { if (empty) { row += empty; empty = 0; } row += p; }
      }
      if (empty) row += empty;
      rows.push(row);
    }
    return rows.join("/");
  }

  function castling(grid) {
    let c = "";
    if (grid[0][4] === "K" && grid[0][7] === "R") c += "K";
    if (grid[0][4] === "K" && grid[0][0] === "R") c += "Q";
    if (grid[7][4] === "k" && grid[7][7] === "r") c += "k";
    if (grid[7][4] === "k" && grid[7][0] === "r") c += "q";
    return c || "-";
  }

  function sideToMove(bottom) {
    const active = document.querySelector(
      ".clock-player-turn, .clock-component.clock-player-turn"
    );
    if (active) {
      const isBottom = active.closest(".clock-bottom") ||
        active.classList.contains("clock-bottom");
      const top = bottom === "white" ? "black" : "white";
      return isBottom ? bottom : top;
    }
    return bottom;
  }

  function hasKings(grid) {
    let w = false, b = false;
    for (const row of grid) for (const p of row) {
      if (p === "K") w = true;
      if (p === "k") b = true;
    }
    return w && b;
  }

  // ------------------------------------------------------------------
  function push(data) {
    GM_xmlhttpRequest({
      method: "POST",
      url: ENDPOINT,
      data: JSON.stringify({ fen: data.fen, color: data.color }),
      headers: { "Content-Type": "application/json" },
      onerror: (e) => {
        console.log(TAG, "POST failed — is run-live.ps1 running?", e);
        setStatus("server offline", "#e05a5a");
      },
      onload: () => {
        console.log(TAG, "sent (" + data.via + "):", data.fen, "color:", data.color);
        setStatus("live (" + data.via + ")", "#48e060");
      },
    });
  }

  function tick() {
    const out = readViaGameApi() || readViaDom();
    if (!out) { setStatus("no board found", "#888"); return; }
    const key = out.fen + "|" + out.color;
    if (key === lastSent) return;
    lastSent = key;
    push(out);
  }

  // --- on-page status pill ---
  let pill;
  function setStatus(text, color) {
    if (!pill) {
      pill = document.createElement("div");
      pill.style.cssText =
        "position:fixed;z-index:2147483647;bottom:8px;right:8px;padding:4px 9px;" +
        "font:12px/1.4 system-ui;border-radius:7px;background:#1c1c1f;color:#fff;" +
        "box-shadow:0 2px 8px rgba(0,0,0,.4);opacity:.9;pointer-events:none";
      (document.body || document.documentElement).appendChild(pill);
    }
    pill.textContent = "chess-auditor: " + text;
    pill.style.borderLeft = "4px solid " + color;
  }

  setStatus("starting…", "#f4c20d");

  // Board mutates on every move; observe it, plus a 1s safety poll
  // (the poll alone is enough — game API reads are cheap).
  const obs = new MutationObserver(() => tick());
  function attach() {
    const b = findBoard();
    if (b) {
      console.log(TAG, "board element found:", b.tagName);
      obs.observe(b, { subtree: true, attributes: true, childList: true });
      tick();
    } else {
      setTimeout(attach, 1000);
    }
  }
  attach();
  setInterval(tick, 1000);
})();
