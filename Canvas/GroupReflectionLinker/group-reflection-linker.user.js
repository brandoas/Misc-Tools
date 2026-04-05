// ==UserScript==
// @name         Group Reflection Linker
// @namespace    https://ohio.instructure.com/
// @version      1.1
// @description  While grading a group assignment in SpeedGrader, injects a panel listing
//               all students in the current group. Each name is a clickable link that opens
//               their individual reflection assignment submission in SpeedGrader.
// @author       brando
// @match        https://ohio.instructure.com/courses/*/gradebook/speed_grader*
// @run-at       document-idle
// ==/UserScript==

// =============================================================================
// DESIGN NOTES
// =============================================================================
//
// PURPOSE
//   When grading a group project, instructors also assign an individual reflection
//   assignment. This script surfaces the group roster directly in SpeedGrader and
//   links each student's name to their personal reflection submission so you can
//   review both without hunting through the gradebook.
//
// HOW TO CONFIGURE (per group assignment)
//   1. Find the reflection assignment ID from its SpeedGrader URL:
//        .../speed_grader?assignment_id=XXXXX
//   2. Open the group assignment in Canvas and add this tag ANYWHERE in the
//      assignment description (invisible to students is fine, e.g. in HTML view):
//        [reflection_id:XXXXX]
//   3. That's it — the script reads the description via the Canvas API and
//      parses the tag automatically.
//
// HOW IT WORKS
//   1. Detects we're in SpeedGrader and parses course ID + assignment ID from URL.
//   2. Fetches the assignment details via Canvas API to find [reflection_id:XXXXX].
//   3. Intercepts history.pushState/replaceState to detect student navigation.
//   4. On each new student, fetches their submission to get the group_id.
//   5. Fetches group membership via /api/v1/groups/:group_id/users.
//   6. Injects a floating panel (bottom-left) with each member's name linked to:
//        /courses/:courseId/gradebook/speed_grader?assignment_id=<reflectionId>&student_id=<userId>
//
// =============================================================================

(function () {
    'use strict';

    const BASE = 'https://ohio.instructure.com';
    const PANEL_ID = 'grl-panel';

    // Cached once on init — these never change during a SpeedGrader session
    let courseId = null;
    let assignmentId = null;

    // Per-page-load cache so we don't re-fetch the same group twice
    const groupCache = {};
    let reflectionAssignmentId = null;
    let lastStudentId = null;

    // -------------------------------------------------------------------------
    // Utilities
    // -------------------------------------------------------------------------

    function getCurrentStudentId() {
        // Try query param first (current Canvas format)
        const fromQuery = new URLSearchParams(window.location.search).get('student_id');
        if (fromQuery) return fromQuery;
        // Fallback: hash JSON used by older Canvas versions — #{"student_id":"12345"}
        try {
            const hash = decodeURIComponent(window.location.hash.slice(1));
            return JSON.parse(hash).student_id || null;
        } catch { return null; }
    }

    async function fetchJson(url) {
        const res = await fetch(url, { credentials: 'include' });
        if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
        return res.json();
    }

    async function fetchAllPages(url) {
        let results = [];
        let nextUrl = url;
        while (nextUrl) {
            const res = await fetch(nextUrl, { credentials: 'include' });
            if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
            const data = await res.json();
            results = results.concat(Array.isArray(data) ? data : [data]);
            const link = res.headers.get('Link') || '';
            const nextMatch = link.match(/<([^>]+)>;\s*rel="next"/);
            nextUrl = nextMatch ? nextMatch[1] : null;
        }
        return results;
    }

    function parseReflectionId(description) {
        if (!description) return null;
        const match = description.match(/\[reflection_id:(\d+)\]/);
        return match ? match[1] : null;
    }

    // -------------------------------------------------------------------------
    // Panel rendering
    // -------------------------------------------------------------------------

    function getOrCreatePanel() {
        let panel = document.getElementById(PANEL_ID);
        if (!panel) {
            panel = document.createElement('div');
            panel.id = PANEL_ID;
            panel.style.cssText = `
                position: fixed;
                bottom: 16px;
                left: 16px;
                width: 250px;
                background: white;
                border: 1px solid #c7cdd1;
                border-radius: 6px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.2);
                font-family: sans-serif;
                font-size: 13px;
                z-index: 99999;
                overflow: hidden;
            `;
            // Inject hover style for member links
            const style = document.createElement('style');
            style.textContent = `#${PANEL_ID} a:hover { text-decoration: underline; }`;
            document.head.appendChild(style);
            document.body.appendChild(panel);
        }
        return panel;
    }

    function renderStatus(panel, type, message) {
        const color = { loading: '#555', info: '#0770A3', warning: '#7a5800', error: '#c0392b' }[type] || '#555';
        panel.innerHTML = `
            <div style="background:#0770A3;color:white;padding:8px 12px;font-weight:bold;font-size:12px;letter-spacing:0.5px;">
                GROUP MEMBERS
            </div>
            <div style="padding:10px 12px;color:${color};font-style:italic;">
                ${message}
            </div>
        `;
    }

    function renderMembers(panel, groupName, members) {
        const countLabel = `${members.length} student${members.length !== 1 ? 's' : ''}`;

        const warningBanner = reflectionAssignmentId ? '' : `
            <div style="background:#fff8e1;border-left:3px solid #f9a825;padding:7px 10px;font-size:11px;color:#7a5800;line-height:1.4;">
                &#9888; No <code>[reflection_id:XXXXX]</code> tag found in assignment description. Names shown but not linked.
            </div>
        `;

        // Hoist the check — reflectionAssignmentId is constant for all members
        const memberRows = reflectionAssignmentId
            ? members.map(user => {
                const href = `${BASE}/courses/${courseId}/gradebook/speed_grader?assignment_id=${reflectionAssignmentId}&student_id=${user.id}`;
                return `
                    <div style="padding:8px 12px;border-bottom:1px solid #f0f0f0;">
                        <a href="${href}" target="_blank"
                           style="color:#0770A3;text-decoration:none;font-weight:500;">
                            ${user.name}
                        </a>
                    </div>`;
            }).join('')
            : members.map(user =>
                `<div style="padding:8px 12px;border-bottom:1px solid #f0f0f0;color:#333;">${user.name}</div>`
            ).join('');

        panel.innerHTML = `
            <div style="background:#0770A3;color:white;padding:8px 12px;font-weight:bold;font-size:12px;letter-spacing:0.5px;display:flex;justify-content:space-between;align-items:center;">
                <span>GROUP MEMBERS</span>
                <span style="font-weight:normal;opacity:0.85;font-size:11px;">${countLabel}</span>
            </div>
            <div style="padding:5px 12px;color:#888;font-size:11px;border-bottom:1px solid #eee;">
                ${groupName || 'Unnamed Group'}
            </div>
            ${warningBanner}
            <div>${memberRows}</div>
        `;
    }

    // -------------------------------------------------------------------------
    // Core logic
    // -------------------------------------------------------------------------

    async function updatePanel() {
        const studentId = getCurrentStudentId();

        // Avoid redundant refreshes when navigation fires but student hasn't changed
        if (studentId === lastStudentId) return;
        lastStudentId = studentId;

        const panel = getOrCreatePanel();

        if (!studentId) {
            renderStatus(panel, 'info', 'No student selected.');
            return;
        }

        renderStatus(panel, 'loading', 'Loading group members\u2026');

        try {
            const submission = await fetchJson(
                `${BASE}/api/v1/courses/${courseId}/assignments/${assignmentId}/submissions/${studentId}?include[]=group`
            );

            const group = submission.group;
            if (!group || !group.id) {
                renderStatus(panel, 'warning', 'No group found for this student.<br>Is this assignment set up as a group assignment?');
                return;
            }

            if (!groupCache[group.id]) {
                groupCache[group.id] = await fetchAllPages(
                    `${BASE}/api/v1/groups/${group.id}/users?per_page=50`
                );
            }

            renderMembers(panel, group.name, groupCache[group.id]);

        } catch (err) {
            renderStatus(panel, 'error', `Error: ${err.message}`);
            console.error('[GRL]', err);
        }
    }

    async function init() {
        const courseMatch = window.location.pathname.match(/\/courses\/(\d+)\//);
        courseId = courseMatch ? courseMatch[1] : null;
        assignmentId = new URLSearchParams(window.location.search).get('assignment_id');
        if (!courseId || !assignmentId) return;

        try {
            const assignment = await fetchJson(
                `${BASE}/api/v1/courses/${courseId}/assignments/${assignmentId}`
            );

            if (!assignment.group_category_id) return; // Not a group assignment — stay silent

            reflectionAssignmentId = parseReflectionId(assignment.description || '');

            await updatePanel();

            // Intercept history mutations — SpeedGrader navigates via pushState/replaceState
            const _pushState = history.pushState.bind(history);
            history.pushState = function (...args) { _pushState(...args); updatePanel(); };

            const _replaceState = history.replaceState.bind(history);
            history.replaceState = function (...args) { _replaceState(...args); updatePanel(); };

            window.addEventListener('popstate', updatePanel);
            window.addEventListener('hashchange', updatePanel); // fallback for older Canvas

        } catch (err) {
            console.error('[GRL] Init error:', err);
        }
    }

    // SpeedGrader is a heavy SPA — give it a moment to settle before we start
    setTimeout(init, 1500);

})();
