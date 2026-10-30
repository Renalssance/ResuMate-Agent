const { createApp } = Vue;

createApp({
    data() {
        return {
            activeNav: 'upload',
            token: localStorage.getItem('accessToken') || '',
            currentUser: null,
            authMode: 'login',
            authForm: {
                username: '',
                password: '',
                role: 'user',
                admin_code: ''
            },
            authLoading: false,

            resumes: [],
            resumesLoading: false,
            selectedResumeFiles: [],
            resumeDragActive: false,
            isUploadingResume: false,
            resumeUploadProgress: '',
            resumeDetail: null,

            jds: [],
            jdsLoading: false,
            jdForm: {
                title: '',
                company: '',
                jd_text: ''
            },
            jdDragActive: false,
            isCreatingJD: false,
            jdCreateProgress: '',
            jdDetail: null,

            matchJDId: '',
            matchResumeId: '',
            isMatching: false,
            matchResult: '',
            matchAbortController: null,
            sessionId: 'session_' + Date.now()
        };
    },

    computed: {
        isAuthenticated() {
            return Boolean(this.token && this.currentUser);
        },

        pageTitle() {
            const titles = {
                upload: '上传资料',
                analysis: '简历匹配分析',
                questions: '试题生成',
                followup: '追问模拟'
            };
            return titles[this.activeNav] || '上传资料';
        },

        pageKicker() {
            const kickers = {
                upload: 'DATA INTAKE',
                analysis: 'MATCH INSIGHT',
                questions: 'QUESTION BUILDER',
                followup: 'FOLLOW-UP SIMULATION'
            };
            return kickers[this.activeNav] || 'DATA INTAKE';
        },

        matchScore() {
            return this.extractMatchScore(this.matchResult);
        },

        matchScoreDisplay() {
            return this.matchScore === null ? '--' : `${this.matchScore}`;
        },

        matchSummary() {
            if (this.isMatching && !this.matchResult) {
                return '正在读取 JD 与简历信息，并生成匹配度判断。';
            }
            if (this.matchScore !== null) {
                if (this.matchScore >= 85) return '匹配度较高，建议重点关注优势项与可验证经历。';
                if (this.matchScore >= 70) return '匹配度良好，建议继续查看差距项和补充理由。';
                if (this.matchScore >= 55) return '存在一定匹配基础，但需要重点确认关键能力缺口。';
                return '匹配度偏低，建议谨慎推进或重新筛选候选人。';
            }
            return '分析完成后将在这里显示匹配度分数与结论。';
        }
    },

    async mounted() {
        this.configureMarked();
        if (this.token) {
            try {
                await this.fetchMe();
                await this.loadInitialData();
            } catch (_) {
                this.handleLogout();
            }
        }
    },

    methods: {
        configureMarked() {
            if (!window.marked) return;
            marked.setOptions({
                highlight(code, lang) {
                    if (!window.hljs) return code;
                    const language = hljs.getLanguage(lang) ? lang : 'plaintext';
                    return hljs.highlight(code, { language }).value;
                },
                langPrefix: 'hljs language-',
                breaks: true,
                gfm: true
            });
        },

        parseMarkdown(text) {
            if (!text) return '';
            if (!window.marked) return this.escapeHtml(text).replace(/\n/g, '<br>');
            return marked.parse(text);
        },

        escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text || '';
            return div.innerHTML;
        },

        authHeaders(extra = {}) {
            const headers = { ...extra };
            if (this.token) headers.Authorization = `Bearer ${this.token}`;
            return headers;
        },

        async authFetch(url, options = {}) {
            const opts = { ...options };
            opts.headers = this.authHeaders(opts.headers || {});
            const response = await fetch(url, opts);
            if (response.status === 401) {
                this.handleLogout();
                throw new Error('登录已过期，请重新登录');
            }
            return response;
        },

        async fetchMe() {
            const response = await this.authFetch('/auth/me');
            if (!response.ok) throw new Error('认证失败');
            this.currentUser = await response.json();
        },

        async loadInitialData() {
            await Promise.all([this.loadResumes(), this.loadJDs()]);
        },

        toggleAuthMode() {
            this.authMode = this.authMode === 'login' ? 'register' : 'login';
            this.authForm.password = '';
            this.authForm.admin_code = '';
        },

        async handleAuthSubmit() {
            if (this.authLoading) return;
            const username = this.authForm.username.trim();
            const password = this.authForm.password.trim();
            if (!username || !password) {
                alert('用户名和密码不能为空');
                return;
            }

            this.authLoading = true;
            try {
                const endpoint = this.authMode === 'login' ? '/auth/login' : '/auth/register';
                const payload = { username, password };
                if (this.authMode === 'register') {
                    payload.role = this.authForm.role;
                    payload.admin_code = this.authForm.admin_code || null;
                }

                const response = await fetch(endpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await response.json().catch(() => ({}));
                if (!response.ok) throw new Error(data.detail || '认证失败');

                this.token = data.access_token;
                this.currentUser = { username: data.username, role: data.role };
                localStorage.setItem('accessToken', this.token);
                this.authForm.password = '';
                this.authForm.admin_code = '';
                this.activeNav = 'upload';
                this.sessionId = 'session_' + Date.now();
                await this.loadInitialData();
            } catch (error) {
                alert(error.message);
            } finally {
                this.authLoading = false;
            }
        },

        handleLogout() {
            this.token = '';
            this.currentUser = null;
            this.activeNav = 'upload';
            this.resumes = [];
            this.jds = [];
            this.selectedResumeFiles = [];
            this.resumeDetail = null;
            this.jdDetail = null;
            this.matchResult = '';
            this.matchJDId = '';
            this.matchResumeId = '';
            localStorage.removeItem('accessToken');
        },

        async showUpload() {
            this.activeNav = 'upload';
            await this.loadInitialData();
        },

        async showAnalysis() {
            this.activeNav = 'analysis';
            this.closeDetails();
            await this.loadInitialData();
        },

        showQuestions() {
            this.activeNav = 'questions';
            this.closeDetails();
        },

        showFollowup() {
            this.activeNav = 'followup';
            this.closeDetails();
        },

        closeDetails() {
            this.resumeDetail = null;
            this.jdDetail = null;
        },

        formatDate(value) {
            if (!value) return '';
            const date = new Date(value);
            if (Number.isNaN(date.getTime())) return '';
            return date.toLocaleDateString('zh-CN');
        },

        formatFileSize(size) {
            if (!size && size !== 0) return '';
            if (size < 1024) return `${size} B`;
            if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
            return `${(size / 1024 / 1024).toFixed(1)} MB`;
        },

        addResumeFiles(files) {
            const allowed = ['pdf', 'doc', 'docx'];
            const incoming = Array.from(files || []).filter(file => {
                const ext = file.name.split('.').pop().toLowerCase();
                return allowed.includes(ext);
            });
            const byKey = new Map(this.selectedResumeFiles.map(file => [`${file.name}_${file.size}`, file]));
            incoming.forEach(file => byKey.set(`${file.name}_${file.size}`, file));
            this.selectedResumeFiles = Array.from(byKey.values());
            this.resumeUploadProgress = incoming.length ? '' : '未识别到可上传的简历文件，请选择 PDF、DOC 或 DOCX。';
        },

        handleResumeFileSelect(event) {
            this.addResumeFiles(event.target.files);
            if (event.target) event.target.value = '';
        },

        handleResumeDrop(event) {
            this.resumeDragActive = false;
            this.addResumeFiles(event.dataTransfer.files);
        },

        clearSelectedResumes() {
            this.selectedResumeFiles = [];
            this.resumeUploadProgress = '';
        },

        async uploadResumes() {
            if (!this.selectedResumeFiles.length || this.isUploadingResume) return;

            this.isUploadingResume = true;
            const total = this.selectedResumeFiles.length;
            const results = [];

            for (let index = 0; index < this.selectedResumeFiles.length; index += 1) {
                const file = this.selectedResumeFiles[index];
                this.resumeUploadProgress = `正在上传第 ${index + 1}/${total} 份简历：${file.name}`;
                try {
                    const formData = new FormData();
                    formData.append('file', file);
                    const response = await this.authFetch('/resume/upload', {
                        method: 'POST',
                        body: formData
                    });
                    const data = await response.json().catch(() => ({}));
                    if (!response.ok) throw new Error(data.detail || '上传失败');
                    results.push(`- ${file.name}：上传成功`);
                } catch (error) {
                    results.push(`- ${file.name}：上传失败（${error.message}）`);
                }
            }

            this.resumeUploadProgress = `简历上传完成\n\n${results.join('\n')}`;
            this.selectedResumeFiles = [];
            this.isUploadingResume = false;
            await this.loadResumes();
        },

        async loadResumes() {
            if (!this.isAuthenticated) return;
            this.resumesLoading = true;
            try {
                const response = await this.authFetch('/resume');
                const data = await response.json().catch(() => ({}));
                if (!response.ok) throw new Error(data.detail || '加载简历失败');
                this.resumes = data.resumes || [];
            } catch (error) {
                alert(`加载简历列表失败：${error.message}`);
            } finally {
                this.resumesLoading = false;
            }
        },

        async viewResumeDetail(id) {
            try {
                const response = await this.authFetch(`/resume/${id}`);
                const data = await response.json().catch(() => ({}));
                if (!response.ok) throw new Error(data.detail || '加载简历详情失败');
                this.resumeDetail = data;
                this.jdDetail = null;
            } catch (error) {
                alert(`加载简历详情失败：${error.message}`);
            }
        },

        async deleteResume(id) {
            if (!confirm('确定删除这份简历吗？')) return;
            try {
                const response = await this.authFetch(`/resume/${id}`, { method: 'DELETE' });
                const data = await response.json().catch(() => ({}));
                if (!response.ok) throw new Error(data.detail || '删除失败');
                this.resumes = this.resumes.filter(resume => resume.id !== id);
                if (this.resumeDetail?.id === id) this.resumeDetail = null;
                if (String(this.matchResumeId) === String(id)) this.matchResumeId = '';
            } catch (error) {
                alert(`删除简历失败：${error.message}`);
            }
        },

        async readTextFile(file) {
            return new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = () => resolve(String(reader.result || ''));
                reader.onerror = () => reject(new Error('文件读取失败'));
                reader.readAsText(file, 'UTF-8');
            });
        },

        async handleJDFileSelect(event) {
            const file = event.target.files?.[0];
            if (event.target) event.target.value = '';
            if (file) await this.loadJDTextFile(file);
        },

        async handleJDDrop(event) {
            this.jdDragActive = false;
            const file = event.dataTransfer.files?.[0];
            if (file) await this.loadJDTextFile(file);
        },

        async loadJDTextFile(file) {
            const ext = file.name.split('.').pop().toLowerCase();
            if (!['txt', 'md', 'markdown'].includes(ext)) {
                this.jdCreateProgress = 'JD 文件仅支持 TXT、MD 或 Markdown。';
                return;
            }
            try {
                this.jdForm.jd_text = await this.readTextFile(file);
                if (!this.jdForm.title) this.jdForm.title = file.name.replace(/\.[^/.]+$/, '');
                this.jdCreateProgress = `已读取文件：${file.name}`;
            } catch (error) {
                this.jdCreateProgress = error.message;
            }
        },

        async createJD() {
            const jdText = this.jdForm.jd_text.trim();
            if (!jdText || jdText.length < 20) {
                alert('请输入完整的 JD 内容，至少 20 个字。');
                return;
            }

            this.isCreatingJD = true;
            this.jdCreateProgress = '正在上传并解析 JD...';
            try {
                const response = await this.authFetch('/jd', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        title: this.jdForm.title.trim(),
                        company: this.jdForm.company.trim(),
                        jd_text: jdText
                    })
                });
                const data = await response.json().catch(() => ({}));
                if (!response.ok) throw new Error(data.detail || '上传 JD 失败');

                this.jdCreateProgress = 'JD 上传并解析成功';
                this.jdForm = { title: '', company: '', jd_text: '' };
                await this.loadJDs();
                this.matchJDId = data.id || this.matchJDId;
                setTimeout(() => {
                    if (this.jdCreateProgress === 'JD 上传并解析成功') this.jdCreateProgress = '';
                }, 2800);
            } catch (error) {
                this.jdCreateProgress = `JD 上传失败：${error.message}`;
            } finally {
                this.isCreatingJD = false;
            }
        },

        async loadJDs() {
            if (!this.isAuthenticated) return;
            this.jdsLoading = true;
            try {
                const response = await this.authFetch('/jd');
                const data = await response.json().catch(() => ({}));
                if (!response.ok) throw new Error(data.detail || '加载 JD 失败');
                this.jds = data.job_descriptions || [];
            } catch (error) {
                alert(`加载 JD 列表失败：${error.message}`);
            } finally {
                this.jdsLoading = false;
            }
        },

        async viewJDDetail(id) {
            try {
                const response = await this.authFetch(`/jd/${id}`);
                const data = await response.json().catch(() => ({}));
                if (!response.ok) throw new Error(data.detail || '加载 JD 详情失败');
                this.jdDetail = data;
                this.resumeDetail = null;
            } catch (error) {
                alert(`加载 JD 详情失败：${error.message}`);
            }
        },

        async deleteJD(id) {
            if (!confirm('确定删除这个 JD 吗？')) return;
            try {
                const response = await this.authFetch(`/jd/${id}`, { method: 'DELETE' });
                const data = await response.json().catch(() => ({}));
                if (!response.ok) throw new Error(data.detail || '删除失败');
                this.jds = this.jds.filter(jd => jd.id !== id);
                if (this.jdDetail?.id === id) this.jdDetail = null;
                if (String(this.matchJDId) === String(id)) this.matchJDId = '';
            } catch (error) {
                alert(`删除 JD 失败：${error.message}`);
            }
        },

        handleMatchJDChange() {
            this.matchResult = '';
        },

        buildMatchPrompt() {
            const jd = this.jds.find(item => String(item.id) === String(this.matchJDId));
            const resume = this.resumes.find(item => String(item.id) === String(this.matchResumeId));
            const jdName = jd ? `${jd.title}${jd.company ? `（${jd.company}）` : ''}` : `ID ${this.matchJDId}`;
            const resumeName = resume ? `${resume.filename}${resume.structured_data?.name ? `（${resume.structured_data.name}）` : ''}` : `ID ${this.matchResumeId}`;

            return [
                `请分析 JD(ID:${this.matchJDId}，${jdName}) 与简历(ID:${this.matchResumeId}，${resumeName}) 的内容匹配程度。`,
                '请结合岗位要求、候选人经历、技能栈、项目经验和风险缺口进行判断。',
                '请严格包含以下结构：',
                '1. 匹配度分数：0-100 分中的一个整数',
                '2. 匹配理由：列出 3-5 条关键依据',
                '3. 主要差距：列出 2-4 条需要核实或补强的点',
                '4. 推进建议：给出是否建议进入下一轮的简洁判断'
            ].join('\n');
        },

        async runMatch() {
            if (!this.matchJDId || !this.matchResumeId || this.isMatching) return;

            this.isMatching = true;
            this.matchResult = '';
            this.matchAbortController = new AbortController();

            try {
                const response = await this.authFetch('/chat/stream', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        message: this.buildMatchPrompt(),
                        session_id: this.sessionId
                    }),
                    signal: this.matchAbortController.signal
                });
                if (!response.ok) throw new Error(`匹配分析请求失败：HTTP ${response.status}`);

                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    buffer += decoder.decode(value, { stream: true });
                    let eventEndIndex;

                    while ((eventEndIndex = buffer.indexOf('\n\n')) !== -1) {
                        const eventStr = buffer.slice(0, eventEndIndex);
                        buffer = buffer.slice(eventEndIndex + 2);
                        this.consumeStreamEvent(eventStr);
                    }
                }
            } catch (error) {
                if (error.name !== 'AbortError') {
                    this.matchResult = `匹配分析失败：${error.message}`;
                }
            } finally {
                this.isMatching = false;
                this.matchAbortController = null;
            }
        },

        consumeStreamEvent(eventStr) {
            const dataLine = eventStr.split('\n').find(line => line.startsWith('data: '));
            if (!dataLine) return;

            const dataStr = dataLine.slice(6);
            if (dataStr === '[DONE]') return;

            try {
                const data = JSON.parse(dataStr);
                if (data.type === 'content') {
                    this.matchResult += data.content;
                } else if (data.type === 'error') {
                    this.matchResult += `\n\n分析过程出错：${data.content}`;
                }
            } catch (_) {
                // Ignore malformed streaming fragments.
            }
        },

        extractMatchScore(text) {
            if (!text) return null;
            const patterns = [
                /匹配度分数\s*[:：]?\s*(\d{1,3})\s*(?:\/\s*100|分|%|％)?/i,
                /匹配度\s*[:：]?\s*(\d{1,3})\s*(?:\/\s*100|分|%|％)?/i,
                /score\s*[:：]?\s*(\d{1,3})\s*(?:\/\s*100|%|％)?/i,
                /(\d{1,3})\s*\/\s*100/
            ];

            for (const pattern of patterns) {
                const match = text.match(pattern);
                if (!match) continue;
                const score = Number(match[1]);
                if (Number.isFinite(score)) return Math.max(0, Math.min(100, score));
            }
            return null;
        }
    }
}).mount('#app');
