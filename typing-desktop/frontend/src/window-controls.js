// Shared by practice and statistics; Vue mounts before DOMContentLoaded.
document.addEventListener('DOMContentLoaded', async () => {
    const desktop = window.__TAURI__.window.getCurrentWindow();
    const maximize = document.querySelector('[data-window-action="maximize"]');
    const updateMaximize = async () => {
        const maximized = await desktop.isMaximized();
        const label = maximized ? '还原' : '最大化';
        maximize.setAttribute('aria-label', label);
        maximize.querySelector('use').setAttribute('href', `/assets/icons.svg#${maximized ? 'restore' : 'maximize'}`);
    };
    const actions = {
        minimize: () => desktop.minimize(),
        maximize: () => desktop.toggleMaximize(),
        close: () => desktop.close()
    };
    document.querySelectorAll('[data-window-action]').forEach(button => {
        button.addEventListener('click', actions[button.dataset.windowAction]);
    });
    await desktop.onResized(updateMaximize);
    await updateMaximize();
});
