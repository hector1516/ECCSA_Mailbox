<script>
	import { onMount } from 'svelte';
	import { auth } from '$lib/stores/auth.js';
	import { avisar } from '$lib/stores/toasts.js';
	import { navigate } from '$lib/router.js';
	import {
		passkeySupported,
		hasPasskeyFlag,
		loginWithPasskey,
		registerPasskey,
		randomDeviceName
	} from '$lib/passkey.js';
	import { revincular, refrescarContador } from '$lib/push.js';

	let correo = $state('');
	let clave = $state('');
	let mostrarClave = $state(false);
	let modo = $state('auto');        // 'auto' | 'password' | 'suggest'
	let cargando = $state(false);
	let sugerenciaNombre = $state('');

	const conPasskey = passkeySupported();

	onMount(() => {
		if (auth.isLoggedIn()) {
			navigate('/', { replace: true });
			return;
		}
		// En iPhone la biometría solo aparece si ya se pidió antes. En escritorio
		// se dispara sola porque pedir permiso con un clic es un paso extra que
		// el usuario no espera.
		if (conPasskey && hasPasskeyFlag() && !esSafariPrivado()) {
			modo = 'auto';
			entrarConPasskey();
		} else {
			modo = 'password';
		}
	});

	/** Modo privado de Safari: localStorage no persiste y rompería la sesión. */
	function esSafariPrivado() {
		try {
			const k = '__mb_test__';
			localStorage.setItem(k, '1');
			localStorage.removeItem(k);
			return false;
		} catch {
			return true;
		}
	}

	async function entrar() {
		if (!correo.trim() || !clave) return;
		cargando = true;
		try {
			await auth.login(correo.trim(), clave);
			await iniciarSesion();
		} catch (e) {
			avisar(e.message || 'No se pudo iniciar sesión', 'error');
			clave = '';
		} finally {
			cargando = false;
		}
	}

	async function entrarConPasskey() {
		cargando = true;
		try {
			await loginWithPasskey();
			await iniciarSesion();
		} catch (e) {
			// Si no hay passkey registrada no es un error para el usuario: se cae
			// al formulario sin decir nada. Cualquier otro motivo sí se avisa.
			avisar(e.message || 'No se pudo iniciar sesión con passkey', 'error');
			modo = 'password';
		} finally {
			cargando = false;
		}
	}

	async function iniciarSesion() {
		// La suscripción push pertenece al service worker pero su asignación es
		// a un usuario: si cambió de cuenta en este teléfono, hay que
		// reenviarla. Es silencioso a propósito (ver push.js).
		await revincular();
		refrescarContador();
		navigate('/', { replace: true });
	}

	async function guardarPasskey() {
		cargando = true;
		try {
			await registerPasskey(sugerenciaNombre || randomDeviceName());
			avisar('Passkey guardada en este equipo', 'success');
			modo = 'password';
		} catch (e) {
			avisar(e.message || 'No se pudo guardar la passkey', 'error');
		} finally {
			cargando = false;
		}
	}

	// Antes de salir de la página: si se está escribiendo con la teclado, se
	// manda el formulario. Sin esto, tocar "Entrar" en el móvil a veces solo
	// quita el foco.
	function alTeclado(e) {
		if (e.key === 'Enter') entrar();
	}
</script>

<div class="login-page">
	<div class="login-card">
		<img class="login-logo" src="/mailbox_logo.png" alt="Mailbox ECCSA" />
		<h1 class="login-title">Mailbox</h1>
		<p class="login-sub">Buzón corporativo ECCSA</p>

		{#if modo === 'suggest'}
			<!-- Pantalla intermedia: entró con contraseña y no tiene passkey. Es
			     el momento en que el Face ID / Touch ID empieza a ser útil. -->
			<div class="login-box">
				<div class="mb-info">
					<div class="mb-info-icon">🔑</div>
					<div>
						<strong>¿Guardar una passkey?</strong>
						<p>Entrás con la huella o el Face ID la próxima vez, sin escribir la contraseña.</p>
					</div>
				</div>
				<input class="input" type="text" bind:value={sugerenciaNombre}
				       placeholder="Nombre de este equipo" maxlength="40" />
				<button class="btn btn-primary btn-block" onclick={guardarPasskey} disabled={cargando}>
					{cargando ? 'Guardando…' : 'Guardar passkey'}
				</button>
				<button class="btn btn-secondary btn-block" onclick={() => modo = 'password'}>
					Ahora no
				</button>
			</div>
		{:else}
			<div class="login-box">
				<input class="input" type="email" bind:value={correo} onkeydown={alTeclado}
				       placeholder="correo@ecc-sa.com.mx" autocapitalize="none"
				       autocomplete="username" inputmode="email" />
				<div class="mb-clave">
					<input class="input" type={mostrarClave ? 'text' : 'password'} bind:value={clave}
					       onkeydown={alTeclado} placeholder="Contraseña"
					       autocomplete="current-password" />
					<button class="btn btn-secondary btn-sm" onclick={() => mostrarClave = !mostrarClave}
					        title={mostrarClave ? 'Ocultar' : 'Mostrar'} tabindex="-1">
						{mostrarClave ? '🙈' : '👁️'}
					</button>
				</div>
				<button class="btn btn-primary btn-block" onclick={entrar} disabled={cargando || !correo || !clave}>
					{cargando ? 'Entrando…' : 'Entrar'}
				</button>

				{#if conPasskey}
					<div class="mb-sep"><span>o</span></div>
					<button class="btn btn-secondary btn-block" onclick={entrarConPasskey} disabled={cargando}>
						🔑 Entrar con passkey
					</button>
				{/if}
			</div>
		{/if}

		<p class="login-foot">Solo personal autorizado por ECCSA</p>
	</div>
</div>

<style>
	/* Todo lo de arriba (colores, fondos, tipografía) viene de app.css, que es el
	   CSS del shell. Solo se estiliza lo que el shell no define: el centrado de
	   la tarjeta de login, la fila del campo de contraseña y el separador.

	   El "or" y la línea punteada entre contraseña y passkey son el separador
	   estándar de formulario; se pinta con un pseudo-elemento para no meter un
	   div vacío en el DOM. */

	.login-page {
		min-height: 100dvh;
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 1.25rem;
	}

	.login-card {
		width: 100%;
		max-width: 24rem;
		text-align: center;
	}

	.login-logo {
		width: 128px;
		height: auto;
		margin: 0 auto 0.75rem;
		display: block;
	}

	.login-title {
		font-size: 1.6rem;
		font-weight: 700;
		margin: 0;
	}

	.login-sub {
		color: var(--color-text-muted);
		font-size: 0.85rem;
		margin: 0.15rem 0 1.5rem;
	}

	.login-box {
		background: var(--color-surface);
		border: 1px solid rgba(255, 255, 255, 0.05);
		border-radius: var(--radius);
		padding: 1.25rem;
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
		text-align: left;
	}

	.login-foot {
		color: var(--color-text-muted);
		font-size: 0.7rem;
		opacity: 0.7;
		margin-top: 1.25rem;
	}

	/* El campo de contraseña con el botón de mostrar/ocultar pegado a la
	   derecha. El grid evita que el input se aplaste en pantallas angostas. */
	.mb-clave {
		display: grid;
		grid-template-columns: 1fr auto;
		gap: 0.5rem;
		align-items: stretch;
	}

	.mb-sep {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		color: var(--color-text-muted);
		font-size: 0.75rem;
	}
	.mb-sep::before,
	.mb-sep::after {
		content: '';
		flex: 1;
		height: 1px;
		background: rgba(255, 255, 255, 0.08);
	}

	.mb-info {
		display: flex;
		gap: 0.75rem;
		align-items: flex-start;
		font-size: 0.85rem;
	}
	.mb-info p {
		margin: 0.15rem 0 0;
		color: var(--color-text-muted);
		font-size: 0.78rem;
		line-height: 1.4;
	}
	.mb-info-icon {
		font-size: 1.5rem;
		line-height: 1;
	}
</style>