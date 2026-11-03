// Settings, media import and sync are shared by both workspace pages.
const workspaceControls = {
    data() {
        return {
            syncModal: { visible: false, loading: false, syncing: false, error: '', status: null },
            resources: { loading: false, transferring: false, status: null, error: '', appliedId: '' },
            // Sync server settings; `required` blocks the page until a first server is saved.
            setup: { visible: false, required: false, url: '', token: '', hasToken: false, editable: true, saving: false, error: '' },
        };
    },
    computed: {
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
        t(zh) { return zh; },
        setupKeydown(event) {
            if (event.key === 'Escape') { this.closeServerSetup(); event.preventDefault(); return; }
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
            if (!file || this.resourceBusy) return;
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
            if (this.setup.required || this.setup.saving || this.resources.transferring) return;
            this.setup.visible = false;
            this.resumeClock?.();
            this.$nextTick(() => this.setupOpener?.focus());
        },

        async saveServerSetup() {
            if (this.setup.saving || this.resourceBusy) return;
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
                this.syncModal.status = response.data.data || null;
            } catch (error) {
                console.error('Error loading sync status:', error);
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
                this.syncModal.status = response.data.data || null;
                await this.afterSync();
            } catch (error) {
                console.error('Error syncing Anki collection:', error);
                const message = error.response?.data?.error || '同步失败';
                this.syncModal.error = message;
                if (error.response?.data?.data) {
                    this.syncModal.status = error.response.data.data;
                }
            } finally {
                this.syncModal.syncing = false;
            }
        },

        formatSyncTime(value) {
            if (!value) {
                return '暂无';
            }
            return new Date(value).toLocaleString('zh-CN', {
                hour12: false,
                timeZone: 'Asia/Shanghai'
            });
        },

        syncHistory() {
            return (this.syncModal.status && this.syncModal.status.history) || [];
        },
    }
};
