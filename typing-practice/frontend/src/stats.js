const { createApp } = Vue;

createApp({
    data() {
        return {
            loading: true,
            stealthMode: false,
            overview: {},
            charts: {},
            // 图表详情弹窗共用这一份状态：掌握度和错误类型点击后只切换 type/items。
            detailModal: {
                visible: false,
                loading: false,
                title: '',
                subtitle: '',
                type: '',
                items: []
            },
            apiBaseUrl: window.location.origin && window.location.origin.startsWith('http')
                ? `${window.location.origin}/api`
                : 'http://localhost:8080/api',
            useMockData: false
        };
    },
    mounted() {
        this.loadStealthMode();
        this.loadAllData();

        window.addEventListener('resize', () => {
            Object.values(this.charts).forEach(chart => {
                if (chart && chart.resize) {
                    chart.resize();
                }
            });
        });
    },
    methods: {
        loadStealthMode() {
            const saved = localStorage.getItem('stealthMode');
            this.stealthMode = saved === 'true';
        },

        toggleStealthMode() {
            this.stealthMode = !this.stealthMode;
            localStorage.setItem('stealthMode', this.stealthMode);
            this.reloadAllCharts();
        },

        async reloadAllCharts() {
            Object.values(this.charts).forEach(chart => {
                if (chart && chart.dispose) {
                    chart.dispose();
                }
            });
            this.charts = {};
            await this.initCharts();
        },

        async loadAllData() {
            this.loading = true;
            try {
                await this.loadOverview();
            } catch (error) {
                console.error('Error loading overview:', error);
                this.loading = false;
                alert('无法加载统计数据，请确保后端服务正在运行');
                return;
            }

            this.loading = false;
            await this.$nextTick();
            await this.initCharts();
        },

        async loadOverview() {
            const response = await axios.get(`${this.apiBaseUrl}/stats/overview`);
            this.overview = response.data.data;
        },

        formatPercent(value) {
            return `${Number(value || 0).toFixed(1)}%`;
        },

        closeDetailModal() {
            this.detailModal.visible = false;
        },

        async openMasteryWords(level, label, count) {
            // 先打开弹窗并展示 loading，再异步请求具体单词，避免用户点击后没有反馈。
            this.detailModal = {
                visible: true,
                loading: true,
                title: label,
                subtitle: `${count || 0} 个单词`,
                type: 'mastery',
                items: []
            };

            try {
                const response = await axios.get(`${this.apiBaseUrl}/stats/mastery-words`, {
                    params: { level, limit: 500 }
                });
                this.detailModal.items = response.data.data || [];
            } finally {
                this.detailModal.loading = false;
            }
        },

        async openErrorTypeWords(errorType, label, count) {
            // 错误类型详情展示的是“最近一次错误输入”和错误次数，便于直接定位问题。
            this.detailModal = {
                visible: true,
                loading: true,
                title: label,
                subtitle: `${count || 0} 次错误`,
                type: 'error',
                items: []
            };

            try {
                const response = await axios.get(`${this.apiBaseUrl}/stats/error-type-words`, {
                    params: { type: errorType, limit: 500 }
                });
                this.detailModal.items = response.data.data || [];
            } finally {
                this.detailModal.loading = false;
            }
        },

        async initCharts() {
            const chartLoaders = [
                ['heatmap', () => this.loadHeatmap()],
                ['accuracy-trend', () => this.loadAccuracyTrend()],
                ['mastery-pie', () => this.loadMasteryPie()],
                ['daily-duration', () => this.loadDailyDuration()],
                ['error-types', () => this.loadErrorTypes()]
            ];

            const results = await Promise.allSettled(chartLoaders.map(([, load]) => load()));
            results.forEach((result, index) => {
                if (result.status === 'rejected') {
                    console.warn(`Failed to load stats chart: ${chartLoaders[index][0]}`, result.reason);
                }
            });
        },

        async loadHeatmap() {
            const container = document.getElementById('heatmap');
            const year = new Date().getFullYear();

            const response = await axios.get(`${this.apiBaseUrl}/stats/heatmap`, {
                params: {
                    start_date: `${year}-01-01`,
                    end_date: `${year}-12-31`
                }
            });

            this.renderHeatmap(container, response.data.data || [], year);
        },

        renderHeatmap(container, data, year) {
            if (!container) {
                return;
            }

            const countsByDate = new Map(data.map((item) => [
                item.date,
                {
                    count: Number(item.count || 0),
                    accuracy: Number(item.accuracy || 0)
                }
            ]));

            const maxCount = Math.max(0, ...data.map((item) => Number(item.count || 0)));
            const monthLabels = this.buildHeatmapMonthLabels(year);
            const weeks = this.buildHeatmapWeeks(year);
            const title = this.stealthMode ? 'Practice Heatmap' : '学习热力图';
            const less = this.stealthMode ? 'Less' : '少';
            const more = this.stealthMode ? 'More' : '多';
            const titleColor = this.stealthMode ? '#374151' : '#4338ca';

            container.innerHTML = `
                <div class="github-heatmap">
                    <div class="github-heatmap-title" style="color: ${titleColor};">${title}</div>
                    <div class="github-heatmap-scroll">
                        <div class="github-heatmap-months">
                            <span></span>
                            ${monthLabels.map((month) => `<span style="grid-column:${month.column};">${month.label}</span>`).join('')}
                        </div>
                        <div class="github-heatmap-body">
                            <div class="github-heatmap-weekdays" aria-hidden="true">
                                <span></span>
                                <span>${this.stealthMode ? 'Mon' : '周一'}</span>
                                <span></span>
                                <span>${this.stealthMode ? 'Wed' : '周三'}</span>
                                <span></span>
                                <span>${this.stealthMode ? 'Fri' : '周五'}</span>
                                <span></span>
                            </div>
                            <div class="github-heatmap-grid" role="grid" aria-label="${title}">
                                ${weeks.map((week) => `
                                    <div class="github-heatmap-week" role="row">
                                        ${week.map((date) => this.renderHeatmapCell(date, countsByDate, maxCount, year)).join('')}
                                    </div>
                                `).join('')}
                            </div>
                        </div>
                    </div>
                    <div class="github-heatmap-footer">
                        <span>${less}</span>
                        ${[0, 1, 2, 3, 4].map((level) => `<span class="github-heatmap-cell github-heatmap-level-${level}"></span>`).join('')}
                        <span>${more}</span>
                    </div>
                </div>
            `;
        },

        renderHeatmapCell(date, countsByDate, maxCount, year) {
            const dateText = this.formatHeatmapDate(date);
            const item = countsByDate.get(dateText) || { count: 0, accuracy: 0 };
            const isCurrentYear = date.getUTCFullYear() === year;
            const level = isCurrentYear ? this.heatmapLevel(item.count, maxCount) : 0;
            const text = this.stealthMode
                ? `${dateText}: ${item.count} practice sessions, ${item.accuracy.toFixed(1)}% accuracy`
                : `${dateText}: ${item.count} 次练习，正确率 ${item.accuracy.toFixed(1)}%`;

            return `<span
                class="github-heatmap-cell github-heatmap-level-${level}${isCurrentYear ? '' : ' github-heatmap-outside'}"
                role="gridcell"
                aria-label="${text}"
                title="${text}"
            ></span>`;
        },

        buildHeatmapWeeks(year) {
            const start = new Date(Date.UTC(year, 0, 1));
            start.setUTCDate(start.getUTCDate() - start.getUTCDay());

            const end = new Date(Date.UTC(year, 11, 31));
            end.setUTCDate(end.getUTCDate() + (6 - end.getUTCDay()));

            const weeks = [];
            for (let cursor = new Date(start); cursor <= end; cursor.setUTCDate(cursor.getUTCDate() + 7)) {
                const week = [];
                for (let day = 0; day < 7; day += 1) {
                    const date = new Date(cursor);
                    date.setUTCDate(cursor.getUTCDate() + day);
                    week.push(date);
                }
                weeks.push(week);
            }
            return weeks;
        },

        buildHeatmapMonthLabels(year) {
            const labels = [];
            const seen = new Set();
            const weeks = this.buildHeatmapWeeks(year);
            const monthNames = this.stealthMode
                ? ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
                : ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月'];

            weeks.forEach((week, index) => {
                const firstInMonth = week.find((date) => date.getUTCFullYear() === year && date.getUTCDate() <= 7);
                if (!firstInMonth) {
                    return;
                }
                const month = firstInMonth.getUTCMonth();
                if (!seen.has(month)) {
                    seen.add(month);
                    labels.push({
                        label: monthNames[month],
                        column: index + 2
                    });
                }
            });

            return labels;
        },

        heatmapLevel(count, maxCount) {
            if (!count) {
                return 0;
            }
            if (maxCount <= 4) {
                return Math.min(4, count);
            }
            if (count <= maxCount * 0.25) {
                return 1;
            }
            if (count <= maxCount * 0.5) {
                return 2;
            }
            if (count <= maxCount * 0.75) {
                return 3;
            }
            return 4;
        },

        formatHeatmapDate(date) {
            return date.toISOString().slice(0, 10);
        },

        async loadAccuracyTrend() {
            const chart = echarts.init(document.getElementById('accuracy-trend'));

            const response = await axios.get(`${this.apiBaseUrl}/stats/accuracy-trend`, {
                params: { days: 30 }
            });

            const data = response.data.data || [];
            const dates = data.map(item => item.date);
            const accuracies = data.map(item => item.accuracy);
            const totals = data.map(item => item.total_words);
            this.renderAccuracyTrend(chart, dates, accuracies, totals);
        },

        renderAccuracyTrend(chart, dates, accuracies, totals) {
            const option = {
                title: {
                    text: this.stealthMode ? 'Accuracy Trend' : '正确率趋势',
                    left: 'center',
                    textStyle: {
                        color: this.stealthMode ? '#374151' : '#4338ca'
                    }
                },
                tooltip: {
                    trigger: 'axis',
                    formatter: (params) => {
                        const index = params[0].dataIndex;
                        const accuracy = Number(params[0].value || 0).toFixed(1);
                        return `${params[0].axisValue}<br/>正确率: ${accuracy}%<br/>练习单词: ${totals[index] || 0}`;
                    }
                },
                xAxis: {
                    type: 'category',
                    data: dates,
                    axisLabel: {
                        rotate: 45,
                        interval: Math.floor(dates.length / 10)
                    }
                },
                yAxis: {
                    type: 'value',
                    min: 0,
                    max: 100,
                    axisLabel: { formatter: '{value}%' }
                },
                series: [{
                    name: '正确率',
                    type: 'line',
                    data: accuracies,
                    smooth: true,
                    itemStyle: {
                        color: this.stealthMode ? '#6b7280' : '#5470c6'
                    },
                    areaStyle: {
                        opacity: 0.3
                    }
                }]
            };

            chart.setOption(option);
            this.charts.accuracyTrend = chart;
        },

        async loadMasteryPie() {
            const chart = echarts.init(document.getElementById('mastery-pie'));

            const response = await axios.get(`${this.apiBaseUrl}/stats/mastery-distribution`);
            const data = response.data.data || { mastered: 0, familiar: 0, learning: 0, weak: 0, new: 0 };
            this.renderMasteryPie(chart, data);
        },

        renderMasteryPie(chart, data) {
            // level 字段不参与 ECharts 展示，但点击扇区时会用它请求后端明细接口。
            const pieData = [
                {
                    value: data.mastered,
                    name: this.stealthMode ? 'Mastered' : '已掌握',
                    level: 'mastered',
                    itemStyle: { color: this.stealthMode ? '#6b7280' : '#67C23A' }
                },
                {
                    value: data.familiar,
                    name: this.stealthMode ? 'Familiar' : '熟悉',
                    level: 'familiar',
                    itemStyle: { color: this.stealthMode ? '#9ca3af' : '#409EFF' }
                },
                {
                    value: data.learning,
                    name: this.stealthMode ? 'Learning' : '学习中',
                    level: 'learning',
                    itemStyle: { color: this.stealthMode ? '#d1d5db' : '#E6A23C' }
                },
                {
                    value: data.weak,
                    name: this.stealthMode ? 'Weak' : '薄弱',
                    level: 'weak',
                    itemStyle: { color: this.stealthMode ? '#4b5563' : '#F56C6C' }
                },
                {
                    value: data.new,
                    name: this.stealthMode ? 'New' : '未学习',
                    level: 'new',
                    itemStyle: { color: this.stealthMode ? '#e5e7eb' : '#909399' }
                }
            ];

            const option = {
                title: {
                    text: this.stealthMode ? 'Word Mastery Distribution' : '单词掌握度分布',
                    left: 'center',
                    textStyle: {
                        color: this.stealthMode ? '#374151' : '#4338ca'
                    }
                },
                tooltip: {
                    trigger: 'item',
                    formatter: '{b}: {c} ({d}%)'
                },
                legend: {
                    orient: 'vertical',
                    left: 'left',
                    top: 'middle'
                },
                series: [{
                    type: 'pie',
                    radius: '60%',
                    data: pieData,
                    emphasis: {
                        itemStyle: {
                            shadowBlur: 10,
                            shadowOffsetX: 0,
                            shadowColor: 'rgba(0, 0, 0, 0.5)'
                        }
                    }
                }]
            };

            chart.setOption(option);
            // 切换摸鱼模式会重新渲染图表，先解绑旧 click，避免重复打开弹窗。
            chart.off('click');
            chart.on('click', (params) => {
                if (params.data && params.data.level) {
                    this.openMasteryWords(params.data.level, params.data.name, params.data.value);
                }
            });
            this.charts.masteryPie = chart;
        },

        async loadDailyDuration() {
            const chart = echarts.init(document.getElementById('daily-duration'));

            const response = await axios.get(`${this.apiBaseUrl}/stats/daily-duration`, {
                params: { days: 30 }
            });

            const data = response.data.data || [];
            const dates = data.map(item => item.date);
            const durations = data.map(item => item.duration_minutes);
            const sessions = data.map(item => item.session_count);
            this.renderDailyDuration(chart, dates, durations, sessions);
        },

        renderDailyDuration(chart, dates, durations, sessions) {
            const option = {
                title: {
                    text: this.stealthMode ? 'Daily Practice Duration' : '每日练习时长',
                    left: 'center',
                    textStyle: {
                        color: this.stealthMode ? '#374151' : '#4338ca'
                    }
                },
                tooltip: {
                    trigger: 'axis',
                    formatter: (params) => {
                        const index = params[0].dataIndex;
                        const minutes = Number(params[0].value || 0).toFixed(1);
                        return `${params[0].axisValue}<br/>时长: ${minutes} 分钟<br/>练习次数: ${sessions[index] || 0}`;
                    }
                },
                xAxis: {
                    type: 'category',
                    data: dates,
                    axisLabel: {
                        rotate: 45,
                        interval: Math.floor(dates.length / 10)
                    }
                },
                yAxis: {
                    type: 'value',
                    axisLabel: { formatter: '{value} min' }
                },
                series: [{
                    name: this.stealthMode ? 'Duration' : '时长',
                    type: 'bar',
                    data: durations,
                    itemStyle: {
                        color: this.stealthMode ? '#6b7280' : '#E6A23C'
                    }
                }]
            };

            chart.setOption(option);
            this.charts.dailyDuration = chart;
        },

        async loadErrorTypes() {
            const chart = echarts.init(document.getElementById('error-types'));

            const response = await axios.get(`${this.apiBaseUrl}/stats/error-types`);
            const data = response.data.data || {};
            this.renderErrorTypes(chart, data);
        },

        renderErrorTypes(chart, data) {
            // errorType 字段保留后端枚举值，点击饼图时按枚举值查询具体错误单词。
            const pieData = [
                {
                    value: data.spelling || 0,
                    name: this.stealthMode ? 'Typo' : '拼写错误',
                    errorType: 'spelling',
                    itemStyle: { color: this.stealthMode ? '#6b7280' : '#F56C6C' }
                },
                {
                    value: data.missing_letter,
                    name: this.stealthMode ? 'Missing Letter' : '漏字母',
                    errorType: 'missing_letter',
                    itemStyle: { color: this.stealthMode ? '#9ca3af' : '#E6A23C' }
                },
                {
                    value: data.extra_letter,
                    name: this.stealthMode ? 'Extra Letter' : '多字母',
                    errorType: 'extra_letter',
                    itemStyle: { color: this.stealthMode ? '#d1d5db' : '#409EFF' }
                },
                {
                    value: data.completely_wrong || 0,
                    name: this.stealthMode ? 'Completely Wrong' : '完全错误',
                    errorType: 'completely_wrong',
                    itemStyle: { color: this.stealthMode ? '#4b5563' : '#909399' }
                },
                {
                    value: data.skipped || 0,
                    name: this.stealthMode ? 'Skipped' : '跳过',
                    errorType: 'skipped',
                    itemStyle: { color: this.stealthMode ? '#e5e7eb' : '#67C23A' }
                }
            ];

            const option = {
                title: {
                    text: this.stealthMode ? 'Error Type Distribution' : '错误类型分布',
                    left: 'center',
                    textStyle: {
                        color: this.stealthMode ? '#374151' : '#4338ca'
                    }
                },
                tooltip: {
                    trigger: 'item',
                    formatter: '{b}: {c} ({d}%)'
                },
                legend: {
                    orient: 'vertical',
                    left: 'left',
                    top: 'middle'
                },
                series: [{
                    type: 'pie',
                    radius: ['40%', '70%'],
                    avoidLabelOverlap: false,
                    data: pieData,
                    emphasis: {
                        itemStyle: {
                            shadowBlur: 10,
                            shadowOffsetX: 0,
                            shadowColor: 'rgba(0, 0, 0, 0.5)'
                        }
                    }
                }]
            };

            chart.setOption(option);
            // 与掌握度图一致，重新渲染前清理旧监听器，保持每次点击只发起一次请求。
            chart.off('click');
            chart.on('click', (params) => {
                if (params.data && params.data.errorType) {
                    this.openErrorTypeWords(params.data.errorType, params.data.name, params.data.value);
                }
            });
            this.charts.errorTypes = chart;
        }
    }
}).mount('#app');
