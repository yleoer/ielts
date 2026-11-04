// Settings, media import, sync and software updates are shared by both pages.
const workspaceControls = {
    data() {
        return {
            syncModal: { visible: false, loading: false, syncing: false, error: '', status: null },
            lastSyncAt: null,
            sidebarCollapsed: false,
            narrowWindow: false,
            resources: { loading: false, transferring: false, status: null, error: '', appliedId: '' },
            updates: { current: '', available: null, phase: 'idle', downloaded: 0, total: 0, error: '' },
            // Sync server settings; `required` blocks the page until a first server is saved.
            setup: { visible: false, required: false, url: '', token: '', hasToken: false, editable: true, saving: false, error: '' },
        };
    },
    computed: {
        updateBusy() { return ['checking', 'downloading', 'installing'].includes(this.updates.phase); },
        updateInstalling() { return ['downloading', 'installing'].includes(this.updates.phase); },
        updateProgress() { return this.updates.total ? Math.floor(this.updates.downloaded * 100 / this.updates.total) : null; },
        syncSummaryText() {
            if (this.syncModal.syncing) return '正在同步…';
            if (!this.lastSyncAt) return '尚未同步';
            const time = new Date(this.lastSyncAt);
            const day = value => value.toLocaleDateString('zh-CN', { timeZone: 'Asia/Shanghai' });
            const options = day(time) === day(new Date())
                ? { hour: '2-digit', minute: '2-digit', hour12: false }
                : { month: 'numeric', day: 'numeric' };
            return `上次 ${time.toLocaleString('zh-CN', { ...options, timeZone: 'Asia/Shanghai' })}`;
        },
        // Narrow windows always use the icon rail; the toggle only applies to wide windows.
        sidebarRail() { return this.sidebarCollapsed || this.narrowWindow; },
        workspaceModalOpen() { return this.setup.visible || this.syncModal.visible; },
        resourceBusy() { return this.resources.transferring || Boolean(this.resources.status?.busy); },
        resourceProgress() {
            const status = this.resources.status;
            return status?.phase === 'uploading' && status.total ? Math.floor(status.done * 100 / status.total) : null;
        },
        resourceProgressText() {
            const status = this.resources.status;
            if (!status) return '';
            if (status.phase === 'installing') return '正在安装…';
            if (status.phase !== 'uploading') return '';
            return `正在导入 ${(status.done / 1048576).toFixed(1)} / ${(status.total / 1048576).toFixed(1)} MiB`;
        },
    },
    methods: {
        // Desktop conventions shared by both pages: shortcuts, collapsible sidebar, no browser reload or context menu.
        initDesktopShell() {
            this.sidebarCollapsed = localStorage.getItem('cijian:sidebar') === 'collapsed';
            const narrow = window.matchMedia('(max-width: 960px)');
            this.narrowWindow = narrow.matches;
            narrow.addEventListener('change', event => { this.narrowWindow = event.matches; });
            this.refreshSyncSummary();
            // The app syncs in the background every few minutes; keep the sidebar time current.
            setInterval(() => { if (!document.hidden) this.refreshSyncSummary(); }, 60000);
            document.addEventListener('visibilitychange', () => { if (!document.hidden) this.refreshSyncSummary(); });
            document.addEventListener('contextmenu', event => event.preventDefault());
            window.addEventListener('keydown', event => this.handleDesktopShortcut(event), true);
        },
        handleDesktopShortcut(event) {
            const ctrl = event.ctrlKey || event.metaKey;
            const reload = event.key === 'F5' || (ctrl && event.key.toLowerCase() === 'r');
            const blocked = reload || (ctrl && ['p', 'f', 'g', 'j', 'u'].includes(event.key.toLowerCase()));
            if (blocked) event.preventDefault();
            if (event.key === 'Escape') {
                if (this.setup.visible) this.closeServerSetup();
                else if (this.syncModal.visible) this.closeSyncModal();
                else if (this.detailModal?.visible) this.closeDetailModal();
                return;
            }
            if (this.workspaceModalOpen) return;
            const pages = { 1: '/index.html', 2: '/stats.html' };
            if (ctrl && !event.shiftKey && !event.altKey && pages[event.key]) {
                event.preventDefault();
                if (location.pathname !== pages[event.key] && !(event.key === '1' && location.pathname === '/')) location.href = pages[event.key];
            } else if (ctrl && event.key.toLowerCase() === 'b' && !this.narrowWindow) {
                event.preventDefault();
                this.toggleSidebar();
            } else if (ctrl && event.key === ',') {
                event.preventDefault();
                this.openServerSetup();
            } else if (reload) {
                return this.refreshPageData();
            }
        },
        toggleSidebar() {
            this.sidebarCollapsed = !this.sidebarCollapsed;
            localStorage.setItem('cijian:sidebar', this.sidebarCollapsed ? 'collapsed' : 'expanded');
        },
        async refreshSyncSummary() {
            this.lastSyncAt = (await axios.get(`${this.apiBaseUrl}/sync/status`)).data.data.last_sync_at;
        },
        async initUpdates() {
            this.updates.current = await window.__TAURI__.app.getVersion();
            await this.checkForUpdates(true);
        },
        async checkForUpdates(silent = false) {
            if (this.updateBusy) return;
            this.updates.phase = 'checking';
            this.updates.error = '';
            try {
                await this.updates.available?.close();
                this.updates.available = null;
                const update = await window.__TAURI__.updater.check({ timeout: 15000 });
                // Tauri resources contain private fields, so keep Vue from proxying them.
                this.updates.available = update ? Vue.markRaw(update) : null;
                this.updates.phase = update ? 'available' : 'current';
            } catch (error) {
                this.updates.phase = 'idle';
                if (!silent) this.updates.error = '检查更新失败，请检查网络后重试。';
            }
        },
        async installUpdate() {
            if (this.updateBusy || this.resourceBusy) return;
            this.updates.error = '';
            if (this.pendingAttempt) {
                this.updates.error = '还有答案未保存，请保存成功后再更新。';
                return;
            }
            Object.assign(this.updates, { phase: 'downloading', downloaded: 0, total: 0 });
            try {
                await this.updates.available.download(event => {
                    if (event.event === 'Started') this.updates.total = event.data.contentLength || 0;
                    if (event.event === 'Progress') this.updates.downloaded += event.data.chunkLength;
                });
                this.saveDraftSession?.();
                this.updates.phase = 'installing';
                // On Windows the updater exits this process and the installer restarts it.
                await this.updates.available.install();
            } catch (error) {
                this.updates.phase = 'available';
                this.updates.error = '更新失败，请稍后重试。';
            }
        },
        setupKeydown(event) {
            if (event.key !== 'Tab') return;
            const controls = [...event.currentTarget.querySelectorAll('button:not(:disabled), input:not(:disabled):not([tabindex="-1"])')];
            const first = controls[0], last = controls[controls.length - 1];
            if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
            else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
        },
        async loadResourceStatus() {
            this.resources.loading = true;
            try {
                const status = (await axios.get(`${this.apiBaseUrl}/resources/status`)).data.data;
                this.resources.status = status;
                if (status.phase === 'ready' && this.resources.appliedId !== status.id) {
                    await this.refreshResourceUrls?.();
                    this.resources.appliedId = status.id;
                }
                this.resources.error = '';
            } catch (error) {
                this.resources.error = error.response?.data?.error || '无法读取资源状态，请重试。';
            } finally {
                this.resources.loading = false;
            }
        },
        async importResources(event) {
            const file = event.target.files?.[0];
            event.target.value = '';
            if (!file || this.resourceBusy || this.updateInstalling) return;
            this.resources.error = '';
            if (!/\.zip$/i.test(file.name) || !file.size) {
                this.resources.error = '请选择非空 ZIP 资源包。'; return;
            }
            this.resources.transferring = true;
            let id;
            try {
                const session = (await axios.post(`${this.apiBaseUrl}/resources/upload`, { size: file.size })).data.data;
                id = session.id;
                for (let offset = 0; offset < file.size; offset += session.chunk_size) {
                    const chunk = await file.slice(offset, offset + session.chunk_size).arrayBuffer();
                    await axios.post(`${this.apiBaseUrl}/resources/chunk?id=${id}&offset=${offset}`, chunk,
                        { headers: { 'Content-Type': 'application/octet-stream' }, timeout: 60000 });
                    this.resources.status = { ...this.resources.status, phase: 'uploading', busy: true, done: Math.min(offset + session.chunk_size, file.size), total: file.size };
                }
                this.resources.status = { ...this.resources.status, phase: 'installing', busy: true };
                await axios.post(`${this.apiBaseUrl}/resources/finish?id=${id}`);
            } catch (error) {
                if (id) { try { await axios.post(`${this.apiBaseUrl}/resources/cancel?id=${id}`); } catch (_) {} }
                this.resources.error = error.response?.data?.error || '导入失败，请重新选择资源包。';
                if (this.resources.status) this.resources.status.busy = false;
                return;
            } finally {
                this.resources.transferring = false;
            }
            await this.loadResourceStatus();
        },
        async cancelResourceUpload() {
            if (this.resources.transferring || this.resources.status?.phase !== 'uploading') return;
            try {
                await axios.post(`${this.apiBaseUrl}/resources/cancel?id=${this.resources.status.id}`);
                await this.loadResourceStatus();
            } catch (error) {
                this.resources.error = error.response?.data?.error || '无法取消导入，请重试。';
            }
        },

        async loadServerSettings() {
            const settings = (await axios.get(`${this.apiBaseUrl}/settings/server`)).data.data;
            Object.assign(this.setup, { url: settings.url || '', token: '', hasToken: settings.has_token, editable: settings.editable, error: '' });
            return settings;
        },

        async openServerSetup() {
            this.setupOpener = document.activeElement;
            this.syncModal.visible = false;
            this.pauseClock?.();
            Object.assign(this.setup, { visible: true, required: false, error: '' });
            try {
                await this.loadServerSettings();
                await this.loadResourceStatus();
                this.$nextTick(() => (this.setup.editable ? this.$refs.serverUrl : this.$refs.resourceChoose)?.focus());
            } catch (error) {
                this.setup.error = '无法加载服务器设置';
            }
        },

        closeServerSetup() {
            if (this.setup.required || this.setup.saving || this.resources.transferring || this.updateInstalling) return;
            this.setup.visible = false;
            this.resumeClock?.();
            this.$nextTick(() => this.setupOpener?.focus());
        },

        async saveServerSetup() {
            if (this.setup.saving || this.resourceBusy || this.updateInstalling) return;
            if (!this.setup.editable) { this.closeServerSetup(); return; }
            this.setup.saving = true;
            this.setup.error = '';
            try {
                await axios.post(`${this.apiBaseUrl}/settings/server`, { url: this.setup.url, token: this.setup.token });
            } catch (error) {
                this.setup.error = error.response?.data?.error || '无法连接同步服务器';
                return;
            } finally {
                this.setup.saving = false;
            }
            const firstRun = this.setup.required;
            Object.assign(this.setup, { visible: false, required: false, token: '' });
            // Bring in the vocabulary and other devices' answers right away.
            await this.openSyncModal();
            await this.syncNow();
            if (firstRun) await this.fetchWords();
        },

        async openSyncModal() {
            this.pauseClock?.();
            this.syncModal.visible = true;
            await this.loadSyncStatus();
        },

        closeSyncModal() {
            this.syncModal.visible = false;
            this.resumeClock?.();
        },

        async loadSyncStatus() {
            this.syncModal.loading = true;
            this.syncModal.error = '';
            try {
                const response = await axios.get(`${this.apiBaseUrl}/sync/status`);
                this.syncModal.status = response.data.data;
                this.lastSyncAt = this.syncModal.status.last_sync_at;
            } catch (error) {
                this.syncModal.error = '无法加载同步状态';
            } finally {
                this.syncModal.loading = false;
            }
        },

        async syncNow() {
            this.syncModal.syncing = true;
            this.syncModal.error = '';
            try {
                const response = await axios.post(`${this.apiBaseUrl}/sync/now`);
                this.syncModal.status = response.data.data;
                this.lastSyncAt = this.syncModal.status.last_sync_at;
                await this.afterSync();
            } catch (error) {
                this.syncModal.error = error.response?.data?.error || '同步失败';
            } finally {
                this.syncModal.syncing = false;
            }
        },

        formatSyncTime(value) {
            return value ? new Date(value).toLocaleString('zh-CN', { hour12: false, timeZone: 'Asia/Shanghai' }) : '暂无';
        },
        syncHistory() { return this.syncModal.status?.history || []; },
    }
};
