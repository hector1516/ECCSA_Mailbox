/* ECCSA-Shell — debug.js — Sistema de debugging con códigos de error únicos */
/* Uso: import { logError, ERROR_CODES } from '$lib/debug.js' */

const APP_PREFIX = 'APP';

export function logError(code, message, context = {}) {
    const error = {
        code,
        message,
        context,
        timestamp: new Date().toISOString(),
        url: typeof window !== 'undefined' ? window.location.href : '',
    };
    console.error(`[${code}] ${message}`, context);

    // Enviar al backend (async, no bloquea UI)
    try {
        const token = localStorage.getItem('admon_token') || localStorage.getItem('field_token');
        if (token) {
            fetch('/api/debug/log', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
                body: JSON.stringify({ codigo: code, app: APP_PREFIX, modulo: code.split('-')[1] || '', mensaje: message, contexto: context, url: error.url }),
            }).catch(() => {});
        }
    } catch (e) {}

    return code;
}

export function logAction(tipo, modulo, accion, datos = {}, duracionMs = null) {
    const entry = {
        app: APP_PREFIX,
        modulo,
        tipo_accion: tipo,
        accion,
        detalle: accion,
        datos,
        duracion_ms: duracionMs,
    };

    fetch('/api/audit/log', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${localStorage.getItem('admon_token') || localStorage.getItem('field_token')}` },
        body: JSON.stringify(entry),
    }).catch(() => {});

    console.log(`[AUDIT] ${APP_PREFIX}-${modulo}-${accion}`, datos);
}

export function logNavigation(from, to) {
    logAction('navigate', '', `nav_${from}_to_${to}`, { from, to });
}

export function logClick(modulo, boton, datos = {}) {
    logAction('click', modulo, `click_${boton}`, datos);
}