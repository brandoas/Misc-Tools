// ==UserScript==
// @name         New Quiz Short Answer Grader
// @namespace    https://ohio.instructure.com/
// @version      0.3
// @description  Adds a grading panel to SpeedGrader for New Quiz short answer / essay questions
// @author       brando
// @match        https://ohio.instructure.com/courses/*/gradebook/speed_grader*
// @match        https://ohio.quiz-lti-pdx-prod.instructure.com/*
// @run-at       document-start
// @grant        GM_setValue
// @grant        GM_getValue
// ==/UserScript==

(function () {
    'use strict';

    // =========================================================
    // CONTEXT A: Quiz LTI iframe — intercept fetch calls and
    // store session_item_results data via GM_setValue
    // =========================================================
    if (window.location.hostname.includes('quiz-lti-pdx-prod')) {
        console.log('[NQG] ✅ script running in quiz-lti iframe:', window.location.href);

        // Show a small visible badge in the iframe so we can confirm injection
        document.addEventListener('DOMContentLoaded', () => {
            const badge = document.createElement('div');
            badge.textContent = '[NQG active]';
            badge.style.cssText = 'position:fixed;bottom:4px;right:4px;background:#0770A3;color:white;font-size:10px;padding:2px 6px;border-radius:3px;z-index:99999;opacity:0.8;';
            document.body?.appendChild(badge);
        });

        function storeItemResults(url, responseText) {
            try {
                const sessionMatch = url.match(/quiz_sessions\/(\w+)/);
                const sessionId = sessionMatch?.[1];
                if (!sessionId) return;
                const data = JSON.parse(responseText);
                GM_setValue(`nqg_items_${sessionId}`, JSON.stringify({ data, ts: Date.now() }));
                console.log('[NQG] ✅ stored session_item_results for session', sessionId, 'data length:', responseText.length);
            } catch (e) {
                console.log('[NQG] ❌ storeItemResults error:', e.message);
            }
        }

        // Hook fetch — log ALL outgoing URLs so we can see what's being called
        const _fetch = window.fetch;
        window.fetch = async function (...args) {
            const url = typeof args[0] === 'string' ? args[0] : (args[0]?.url || '');
            console.log('[NQG] fetch:', url);
            const response = await _fetch.apply(this, args);
            if (url.includes('session_item_results')) {
                response.clone().text().then(t => storeItemResults(url, t)).catch(e => console.log('[NQG] clone error:', e));
            }
            return response;
        };

        // Hook XHR — log ALL outgoing URLs
        const _open = XMLHttpRequest.prototype.open;
        const _send = XMLHttpRequest.prototype.send;
        XMLHttpRequest.prototype.open = function (method, url, ...rest) {
            this._nqgUrl = url;
            console.log('[NQG] XHR:', method, url);
            return _open.call(this, method, url, ...rest);
        };
        XMLHttpRequest.prototype.send = function (...args) {
            if (this._nqgUrl && this._nqgUrl.includes('session_item_results')) {
                this.addEventListener('load', function () {
                    storeItemResults(this._nqgUrl, this.responseText);
                });
            }
            return _send.apply(this, args);
        };

        return;
    }

    // =========================================================
    // CONTEXT B: Main Canvas SpeedGrader page
    // =========================================================

    const BASE = 'https://ohio.instructure.com';

    function parseIds() {
        const courseMatch = window.location.pathname.match(/\/courses\/(\d+)\//);
        const courseId = courseMatch ? courseMatch[1] : null;
        const assignmentId = new URLSearchParams(window.location.search).get('assignment_id');
        return { courseId, assignmentId };
    }

    async function fetchAllPages(url) {
        let results = [];
        let nextUrl = url;
        while (nextUrl) {
            const res = await fetch(nextUrl, { credentials: 'include' });
            if (!res.ok) throw new Error(`${res.status} ${res.statusText} — ${nextUrl}`);
            const data = await res.json();
            results = results.concat(Array.isArray(data) ? data : [data]);
            const link = res.headers.get('Link') || '';
            const nextMatch = link.match(/<([^>]+)>;\s*rel="next"/);
            nextUrl = nextMatch ? nextMatch[1] : null;
        }
        return results;
    }

    function parseQuizSessionId(url) {
        if (!url) return null;
        try {
            const outer = new URL(url);
            const inner = decodeURIComponent(outer.searchParams.get('url') || '');
            const match = inner.match(/quiz_session_id=(\d+)/);
            return match ? match[1] : null;
        } catch { return null; }
    }

    function stripHtml(html) {
        const div = document.createElement('div');
        div.innerHTML = html;
        return div.textContent || div.innerText || '';
    }

    async function loadAndDisplay() {
        const { courseId, assignmentId } = parseIds();
        if (!courseId || !assignmentId) {
            alert('Could not parse course/assignment ID from URL.');
            return;
        }

        const win = window.open('', '_blank');
        win.document.title = 'Short Answer Grader — Loading...';
        const initStyle = win.document.createElement('style');
        initStyle.textContent = 'body{font-family:sans-serif;padding:20px;background:#f5f5f5}#status{color:#555;font-style:italic;margin-bottom:20px}';
        win.document.head.appendChild(initStyle);
        const h2 = win.document.createElement('h2');
        h2.textContent = 'New Quiz Short Answer Grader';
        const statusEl = win.document.createElement('div');
        statusEl.id = 'status';
        statusEl.textContent = 'Loading...';
        const contentEl = win.document.createElement('div');
        contentEl.id = 'content';
        win.document.body.append(h2, statusEl, contentEl);

        const setStatus = msg => { const el = win.document.getElementById('status'); if (el) el.textContent = msg; };

        try {
            setStatus('Fetching quiz questions...');
            const items = await fetchAllPages(`${BASE}/api/quiz/v1/courses/${courseId}/quizzes/${assignmentId}/items`);

            const manualItems = items.filter(i => i?.entry?.interaction_type_slug === 'essay');
            if (manualItems.length === 0) {
                setStatus('No essay questions found in this quiz.');
                return;
            }

            setStatus('Fetching submissions...');
            const submissions = await fetchAllPages(
                `${BASE}/api/v1/courses/${courseId}/assignments/${assignmentId}/submissions?per_page=100`
            );

            setStatus('Fetching student roster...');
            const users = await fetchAllPages(
                `${BASE}/api/v1/courses/${courseId}/users?enrollment_type[]=student&per_page=100`
            );
            const userMap = {};
            users.forEach(u => { userMap[u.id] = u.name; });

            // Build map: item_id -> [ { name, answer } ]
            const responsesByItem = {};
            manualItems.forEach(item => { responsesByItem[item.id] = []; });

            const submittedSubs = submissions.filter(s => s.submitted_at && s.workflow_state !== 'unsubmitted');
            let captured = 0;

            setStatus('Reading captured responses from SpeedGrader...');
            for (const sub of submittedSubs) {
                const sessionId = parseQuizSessionId(sub.url);
                if (!sessionId) continue;

                const stored = GM_getValue(`nqg_items_${sessionId}`, null);
                if (!stored) continue;

                captured++;
                const { data } = JSON.parse(stored);
                const name = userMap[sub.user_id] || `User ${sub.user_id}`;

                const itemResults = Array.isArray(data) ? data
                    : (data.session_item_results || data.item_results || []);

                itemResults.forEach(ir => {
                    const itemId = ir.quiz_item_id || ir.item_id;
                    if (responsesByItem[itemId] !== undefined) {
                        const answer = ir?.scored_data?.value
                            || ir?.response?.value
                            || ir?.answer
                            || '(no text found — raw: ' + JSON.stringify(ir).slice(0, 100) + ')';
                        responsesByItem[itemId].push({ name, answer });
                    }
                });
            }

            // Debug: show what's in GM storage
            const gmKeys = submittedSubs.map(s => {
                const sid = parseQuizSessionId(s.url);
                const val = sid ? GM_getValue(`nqg_items_${sid}`, null) : null;
                return `session ${sid}: ${val ? 'FOUND (ts=' + JSON.parse(val).ts + ')' : 'MISSING'}`;
            });
            win.console.log('[NQG] GM storage check:\n' + gmKeys.join('\n'));

            setStatus('');
            renderResults(win, manualItems, submissions, responsesByItem, captured, submittedSubs.length, gmKeys);

        } catch (err) {
            setStatus(`Error: ${err.message}`);
            console.error(err);
        }
    }

    function renderResults(win, manualItems, submissions, responsesByItem, captured, total, gmKeys = []) {
        const doc = win.document;
        doc.title = 'Short Answer Grader';

        const style = doc.createElement('style');
        style.textContent = `
            body { font-family: sans-serif; padding: 20px; background: #f5f5f5; color: #222; }
            h2 { color: #0770A3; }
            .question-block { background: white; border-left: 4px solid #0770A3; border-radius: 4px;
                              padding: 16px 20px; margin-bottom: 24px; box-shadow: 0 1px 4px rgba(0,0,0,0.1); }
            .question-header { font-weight: bold; font-size: 16px; margin-bottom: 12px; }
            .question-pts { color: #888; font-weight: normal; font-size: 13px; }
            .question-text { color: #444; font-size: 13px; margin-bottom: 12px; border-bottom: 1px solid #eee; padding-bottom: 10px; }
            .response { border-top: 1px solid #eee; padding: 10px 0; }
            .student-name { font-weight: bold; color: #333; font-size: 13px; }
            .student-answer { color: #555; font-size: 14px; margin-top: 4px; white-space: pre-wrap; }
            .no-responses { color: #aaa; font-style: italic; font-size: 13px; }
            .meta { font-size: 12px; color: #999; margin-bottom: 16px; }
            .notice { background: #fff8e1; border-left: 4px solid #f9a825; padding: 10px 14px;
                      border-radius: 4px; font-size: 13px; margin-bottom: 20px; }
            .diag { background: #1e1e1e; color: #ccc; font-family: monospace; font-size: 11px;
                    padding: 10px 14px; border-radius: 4px; margin-bottom: 20px; white-space: pre-wrap; }
            .diag-header { font-weight: bold; color: #888; font-size: 12px; margin-bottom: 4px; }
        `;
        doc.head.appendChild(style);

        const content = doc.getElementById('content');
        const pending = submissions.filter(s => s.workflow_state === 'pending_review').length;

        content.innerHTML = `<p class="meta">
            ${manualItems.length} essay question(s) &nbsp;|&nbsp;
            ${pending} / ${submissions.filter(s => s.submitted_at).length} pending review &nbsp;|&nbsp;
            ${captured} / ${total} responses captured
        </p>`;

        if (gmKeys.length > 0) {
            const diagEl = doc.createElement('div');
            diagEl.innerHTML = `<div class="diag-header">GM Storage Debug (first 10)</div><div class="diag">${gmKeys.slice(0, 10).join('\n')}</div>`;
            content.appendChild(diagEl);
        }

        if (captured < total) {
            const notice = doc.createElement('div');
            notice.className = 'notice';
            notice.textContent = `${total - captured} student(s) not yet captured. In SpeedGrader, click through each student to load their quiz — then re-click "Grade Short Answers".`;
            content.appendChild(notice);
        }

        manualItems.forEach((item, idx) => {
            const pos = item.position || (idx + 1);
            const pts = item.points_possible || '?';
            const questionText = stripHtml(item?.entry?.item_body || '');

            const block = doc.createElement('div');
            block.className = 'question-block';
            block.innerHTML = `
                <div class="question-header">Question ${pos} <span class="question-pts">(${pts} pts)</span></div>
                <div class="question-text">${questionText}</div>
            `;

            const responses = responsesByItem[item.id] || [];
            if (responses.length === 0) {
                const empty = doc.createElement('div');
                empty.className = 'no-responses';
                empty.textContent = '(no responses captured yet)';
                block.appendChild(empty);
            } else {
                responses.forEach(({ name, answer }) => {
                    const responseEl = doc.createElement('div');
                    responseEl.className = 'response';
                    responseEl.innerHTML = `
                        <div class="student-name">${name}</div>
                        <div class="student-answer">${answer}</div>
                    `;
                    block.appendChild(responseEl);
                });
            }

            content.appendChild(block);
        });
    }

    // Auto-capture: clicks SpeedGrader's next-student button on a timer
    async function autoCapture(statusBtn) {
        // Find the next-student button (try common Canvas selectors)
        const nextBtn = document.querySelector(
            '#next-student-button, .next-student-button, [data-action="next-student"], button[title*="next" i], button[aria-label*="next student" i]'
        );
        if (!nextBtn) {
            alert('Could not find SpeedGrader next-student button. Try clicking students manually.');
            return;
        }

        const DELAY = 4000; // ms to wait per student for quiz to load
        let count = 0;

        // Determine total students from page if available
        const totalEl = document.querySelector('#x_of_x_students_frd, .student_count');
        const totalGuess = totalEl ? parseInt(totalEl.textContent.match(/\d+/)?.[0] || '0') : 60;

        for (let i = 0; i < totalGuess; i++) {
            count++;
            statusBtn.textContent = `Capturing ${count}/${totalGuess}… (wait)`;
            await new Promise(r => setTimeout(r, DELAY));
            if (nextBtn.disabled || nextBtn.getAttribute('aria-disabled') === 'true') break;
            nextBtn.click();
        }

        statusBtn.textContent = 'Grade Short Answers';
        statusBtn.disabled = false;
        loadAndDisplay();
    }

    // --- Inject Buttons ---
    function injectButton() {
        if (document.getElementById('nqg-btn')) return;

        const wrap = document.createElement('div');
        wrap.style.cssText = `
            position: fixed; top: 12px; left: 50%; transform: translateX(-50%);
            z-index: 99999; display: flex; gap: 8px;
        `;

        const btn = document.createElement('button');
        btn.id = 'nqg-btn';
        btn.textContent = 'Grade Short Answers';
        btn.style.cssText = `
            padding: 8px 14px; background: #0770A3; color: white;
            border: none; border-radius: 4px; font-size: 14px;
            cursor: pointer; box-shadow: 0 2px 6px rgba(0,0,0,0.3);
        `;
        btn.addEventListener('click', loadAndDisplay);

        const captureBtn = document.createElement('button');
        captureBtn.id = 'nqg-capture-btn';
        captureBtn.textContent = 'Auto-Capture All';
        captureBtn.style.cssText = `
            padding: 8px 14px; background: #1B7A34; color: white;
            border: none; border-radius: 4px; font-size: 14px;
            cursor: pointer; box-shadow: 0 2px 6px rgba(0,0,0,0.3);
        `;
        captureBtn.addEventListener('click', () => {
            captureBtn.disabled = true;
            captureBtn.textContent = 'Starting…';
            autoCapture(captureBtn);
        });

        wrap.appendChild(btn);
        wrap.appendChild(captureBtn);
        document.body.appendChild(wrap);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', injectButton);
    } else {
        injectButton();
    }

})();
