<template>
  <div class="page-stack applications-page">
    <section v-if="submissionVersionId" class="card submission-choice" aria-label="关联已确认版本">
      <div class="section-head"><div><p class="submission-eyebrow">本次投递材料</p><h2>关联已确认版本</h2><p>选择一条投递记录，保存本次提交的固定材料。</p></div><RouterLink v-if="selectedVersion" class="button-secondary" :to="`/resume-versions/${selectedVersion.id}`">返回确认版本</RouterLink></div>
      <p v-if="submissionLoading" role="status">正在读取确认版本…</p>
      <p v-if="submissionError" class="error-note" role="alert">{{ submissionError }}</p>
      <template v-if="selectedVersion">
        <div class="submission-fixed"><strong>已确认版本 · 第 {{ selectedVersion.revision }} 版</strong><p>关联后会保留提交时的正文；以后更新主简历不会改变这份记录。</p></div>
        <details class="submission-preview"><summary>查看将要关联的材料</summary><ResumePreview :resume="confirmedContent(selectedVersion.structuredContent)" title="本次固定材料" /></details>
        <div class="submission-options">
          <div><h3>记录一次新投递</h3><p>填写公司和岗位，同时保存这份材料。</p><button class="button-primary" type="button" :disabled="store.saving" @click="beginNewSubmission">新建投递并关联</button></div>
          <form @submit.prevent="attachExistingSubmission"><h3>关联到已有投递</h3><label class="form-field"><span>已有投递</span><select v-model="existingApplicationId" aria-label="已有投递" required :disabled="store.saving"><option value="">请选择投递记录</option><option v-for="application in availableSubmissions" :key="application.id" :value="application.id">{{ application.company }} · {{ application.position }}</option></select></label><p v-if="!availableSubmissions.length">暂无可关联的记录，可以新建投递。</p><button class="button-secondary" type="submit" :disabled="!existingApplicationId || store.saving">{{ store.saving ? '正在关联…' : '关联到此投递' }}</button></form>
        </div>
        <p v-if="store.error" class="error-note" role="alert">{{ store.error }}</p>
      </template>
    </section>
    <p v-if="submissionNotice" class="submission-notice" role="status">{{ submissionNotice }}</p>
    <section class="stats-grid application-stats-grid">
      <button
        class="metric-card application-metric total"
        type="button"
        aria-haspopup="dialog"
        aria-controls="application-metric-details"
        @click="openMetricDetails('company', '投递公司')"
      >
        <span>投递公司</span>
        <div class="application-metric-counts">
          <div>
            <strong>{{ applicationSummary.companyCount }}</strong>
            <small>累计</small>
          </div>
          <div>
            <strong>{{ applicationSummary.inProgress.companyCount }}</strong>
            <small>流程中</small>
          </div>
        </div>
        <div class="metric-card-foot">
          <small>公司去重 · 共 {{ store.totalCount }} 条投递</small>
        </div>
        <div class="metric-stack" aria-label="投递状态构成">
          <span
            v-for="segment in statusSegments"
            :key="segment.key"
            :class="segment.tone"
            :style="{ flexBasis: `${segment.percent}%` }"
          ></span>
        </div>
      </button>
      <button
        v-for="metric in stageMetrics"
        :key="metric.label"
        :class="['metric-card', 'glass-surface', 'application-metric', metric.tone]"
        type="button"
        aria-haspopup="dialog"
        aria-controls="application-metric-details"
        @click="openMetricDetails(metric.key, metric.label)"
      >
        <span>{{ metric.label }}</span>
        <div class="application-metric-counts">
          <div>
            <strong>{{ metric.count }}</strong>
            <small>累计</small>
          </div>
          <div v-if="metric.activeCount !== undefined">
            <strong>{{ metric.activeCount }}</strong>
            <small>流程中</small>
          </div>
        </div>
        <div class="metric-card-foot">
          <small>累计占总投递</small>
          <small>{{ metric.percent }}%</small>
        </div>
        <div :class="['metric-mini-track', metric.tone]" aria-hidden="true">
          <span :style="{ width: `${metric.percent}%` }"></span>
        </div>
      </button>
    </section>

    <dialog
      id="application-metric-details"
      ref="metricDialog"
      class="application-metric-dialog"
      aria-labelledby="application-metric-details-title"
      @click.self="closeMetricDetails"
      @close="selectedMetric = null"
    >
      <section class="application-metric-panel">
        <header class="application-metric-panel-head">
          <div>
            <h2 id="application-metric-details-title">{{ selectedMetric?.label }} · 累计记录</h2>
            <p>共 {{ metricCompanyGroups.length }} 家公司 · {{ metricDetailRecords.total.length }} 条投递</p>
            <small class="application-metric-legend">红色表示有未完成的测评、笔试或面试日程</small>
          </div>
          <button class="icon-button" type="button" aria-label="关闭统计详情" @click="closeMetricDetails">
            <X class="app-icon" aria-hidden="true" />
          </button>
        </header>
        <div class="application-metric-panel-body">
          <EmptyState
            v-if="!metricCompanyGroups.length"
            title="暂无累计记录"
            description="该分类下还没有公司和岗位。"
          />
          <section v-for="group in metricCompanyGroups" :key="group.company" class="application-metric-company">
            <h3 :class="{ 'is-in-progress': group.applications.some((item) => metricActiveIds.has(item.id)) }">
              {{ group.company }}
            </h3>
            <ul>
              <li
                v-for="application in group.applications"
                :key="application.id"
                :class="{ 'is-in-progress': metricActiveIds.has(application.id) }"
              >
                <strong :title="application.position">{{ application.position }}</strong>
                <span v-if="metricActiveIds.has(application.id)" class="application-metric-progress-label">流程中</span>
                <span v-else>{{ applicationStatusLabel(application.status) }}</span>
              </li>
            </ul>
          </section>
        </div>
      </section>
    </dialog>

    <section class="card application-schedule-card">
      <div class="section-head compact">
        <div>
          <h2>日程日历</h2>
          <p>按日期查看笔试、面试和测评安排。</p>
        </div>
        <div class="schedule-calendar-toolbar" aria-label="日历月份导航">
          <button class="button-secondary" type="button" @click="goToCurrentMonth">今天</button>
          <div class="schedule-calendar-pagination">
            <button type="button" aria-label="上个月" @click="changeCalendarMonth(-1)"><ChevronLeft class="app-icon" aria-hidden="true" /></button>
            <strong>{{ calendarMonthLabel }}</strong>
            <button type="button" aria-label="下个月" @click="changeCalendarMonth(1)"><ChevronRight class="app-icon" aria-hidden="true" /></button>
          </div>
        </div>
      </div>

      <div class="schedule-calendar">
        <div class="schedule-calendar-weekdays" aria-hidden="true">
          <span v-for="weekday in calendarWeekdays" :key="weekday">{{ weekday }}</span>
        </div>
        <div class="schedule-calendar-grid" :aria-label="calendarMonthLabel">
          <button
            v-for="day in calendarDays"
            :key="day.key"
            :class="[
              'schedule-calendar-day',
              {
                outside: !day.isCurrentMonth,
                today: day.isToday,
                past: day.isPast,
                selected: day.key === selectedDateKey,
                'has-schedules': day.schedules.length,
              },
            ]"
            type="button"
            :aria-label="calendarDayAriaLabel(day)"
            :aria-pressed="day.key === selectedDateKey"
            @click="selectCalendarDay(day)"
          >
            <span class="schedule-calendar-day-head">
              <span class="schedule-calendar-date">{{ day.dayNumber }}</span>
              <span v-if="day.isToday" class="schedule-calendar-today-label">今天</span>
            </span>
            <span class="schedule-calendar-events">
              <span
                v-for="schedule in day.schedules.slice(0, 4)"
                :key="schedule.id"
                :class="[
                  'schedule-calendar-event',
                  `category-${getScheduleCalendarCategory(schedule.status).key}`,
                  `position-${schedule.calendarPosition}`,
                  { completed: schedule.isCompleted },
                ]"
                :title="`${schedule.applicationLabel} · ${schedule.title}`"
              >
                <template v-if="schedule.calendarPosition === 'middle'">
                  <span class="schedule-calendar-event-company">{{ schedule.companyShortName }}</span>
                </template>
                <template v-else>
                  <span
                    v-if="schedule.calendarPosition === 'single'"
                    class="schedule-calendar-event-dot"
                    aria-hidden="true"
                  ></span>
                  <ArrowLeft v-if="schedule.calendarPosition === 'end'" class="app-icon schedule-calendar-event-arrow" aria-hidden="true" />
                  <span v-if="schedule.calendarPosition !== 'single'" class="schedule-calendar-event-company">
                    {{ schedule.companyShortName }}
                  </span>
                  <span class="schedule-calendar-event-title">{{ getScheduleCalendarCategory(schedule.status).label }}</span>
                  <ArrowRight v-if="schedule.calendarPosition === 'start'" class="app-icon schedule-calendar-event-arrow" aria-hidden="true" />
                </template>
              </span>
              <span v-if="day.schedules.length > 4" class="schedule-calendar-more">+{{ day.schedules.length - 4 }}</span>
            </span>
          </button>
        </div>
      </div>

      <section class="schedule-calendar-agenda" aria-live="polite">
        <header class="schedule-calendar-agenda-head">
          <div>
            <strong>{{ selectedDateLabel }}</strong>
            <span>{{ selectedDateSchedules.length }} 项日程</span>
          </div>
        </header>

        <p v-if="store.loading && !store.applications.length" class="loading-state" role="status">正在加载日程…</p>
        <EmptyState
          v-else-if="!selectedDateSchedules.length && !store.error"
          title="当天暂无日程"
          description="选择其他日期，或在投递记录中添加新的日程。"
        />
        <article
          v-for="schedule in selectedDateSchedules"
          :key="schedule.id"
          :class="['schedule-agenda-item', scheduleTone(schedule)]"
        >
          <span :class="['schedule-agenda-rail', statusTone(schedule.status)]" aria-hidden="true"></span>
          <div class="schedule-agenda-main">
            <strong>{{ schedule.title }}</strong>
            <span>{{ schedule.applicationLabel }}</span>
          </div>
          <time class="schedule-time">{{ formatDateTimeRange(schedule.startsAt, schedule.endsAt) }}</time>
          <span :class="['application-status-pill', statusTone(schedule.status)]">
            {{ applicationStatusLabel(schedule.status) }}
          </span>
          <p class="schedule-note">
            <template v-if="schedule.isCompleted">已写入时间线</template>
            <template v-else>
              <template v-for="(part, index) in scheduleNoteParts(schedule.note || '未添加备注')" :key="`${schedule.id}-${index}`">
                <a v-if="part.type === 'link'" :href="part.value" target="_blank" rel="noreferrer">{{ part.value }}</a>
                <span v-else>{{ part.value }}</span>
              </template>
            </template>
          </p>
          <button
            v-if="!schedule.isCompleted"
            class="button-secondary schedule-complete-button"
            type="button"
            :disabled="isCompletingSchedule(schedule.id)"
            @click="completeSchedule(schedule)"
          >
            <Save class="app-icon" aria-hidden="true" />
            <span>{{ isCompletingSchedule(schedule.id) ? '完成中' : '完成' }}</span>
          </button>
        </article>
      </section>
    </section>

    <section class="card application-list-card">
      <div class="section-head compact">
        <div>
          <h2>投递记录</h2>
          <p>用“记录状态”追加测评、笔试、面试和结果节点。</p>
        </div>
        <div class="application-list-actions">
          <button
            class="button-secondary"
            type="button"
            title="导出全部投递记录"
            :disabled="store.loading || exporting || !store.applications.length"
            @click="exportRecords"
          >
            <Save class="app-icon" aria-hidden="true" />
            <span>{{ exporting ? '导出中...' : '导出记录' }}</span>
          </button>
          <button v-if="!editingId" class="button-secondary" type="button" @click="toggleApplicationForm">
            <component :is="showApplicationForm ? X : Plus" class="app-icon" aria-hidden="true" />
            <span>{{ showApplicationForm ? '收起新增' : '新增投递' }}</span>
          </button>
        </div>
      </div>
      <p v-if="exportError" class="error-note" role="alert">{{ exportError }}</p>
      <p v-if="interviewError" class="error-note" role="alert">{{ interviewError }}</p>

      <div v-if="showApplicationForm" class="application-entry-panel">
        <div class="section-head compact">
          <div>
            <h3>新增投递</h3>
            <p>记录公司、岗位、投递日期、关联简历和当前进展。</p>
          </div>
        </div>

        <form class="application-form" @submit.prevent="submitApplication">
          <label class="form-field application-field application-company">
            <span>公司</span>
            <input v-model.trim="form.company" required placeholder="例如：字节跳动" />
          </label>
          <label class="form-field application-field application-position">
            <span>岗位</span>
            <input v-model.trim="form.position" required placeholder="例如：后端开发工程师" />
          </label>
          <label class="form-field application-field application-date">
            <span>投递日期</span>
            <input v-model="form.applied_date" required type="date" />
          </label>
          <label class="form-field application-field application-status">
            <span>初始状态</span>
            <select v-model="form.status">
              <option v-for="item in applicationStatusOptions" :key="item.value" :value="item.value">
                {{ item.label }}
              </option>
            </select>
          </label>
          <div v-if="selectedVersion" class="form-field application-field application-resume submission-fixed"><span>本次固定材料</span><strong>已确认版本 · 第 {{ selectedVersion.revision }} 版</strong></div>
          <label v-else class="form-field application-field application-resume">
            <span>关联简历</span>
            <select v-model="form.resume_id">
              <option :value="null">不关联</option>
              <option v-for="resume in parsedResumes" :key="resume.id" :value="resumeNumericId(resume.id)">
                {{ resume.filename }}
              </option>
            </select>
          </label>
          <label class="form-field application-field application-link">
            <span>投递链接</span>
            <input v-model.trim="form.job_url" type="url" placeholder="https://..." />
          </label>
          <label class="form-field application-field application-source">
            <span>来源</span>
            <input v-model.trim="form.source" placeholder="官网 / Boss / 内推 / 猎头" />
          </label>
          <label class="form-field application-field application-notes">
            <span>备注</span>
            <input v-model.trim="form.notes" placeholder="简历版本、联系人、下一步动作等" />
          </label>
          <div class="form-actions application-submit">
            <button class="button-secondary" type="button" :disabled="store.saving" @click="resetForm">取消</button>
            <button class="button-primary" type="submit" :disabled="store.saving">
              <Plus class="app-icon" aria-hidden="true" />
              <span>{{ store.saving ? '保存中...' : selectedVersion ? '添加并关联' : '添加记录' }}</span>
            </button>
          </div>
        </form>

        <p v-if="store.error" class="error-note">{{ store.error }}</p>
      </div>

      <div class="form-filter-panel application-filters">
        <label class="form-field">
          <span>状态</span>
          <select v-model="statusFilter">
            <option v-for="item in applicationStatusFilterOptions" :key="item.value" :value="item.value">
              {{ item.label }}
            </option>
          </select>
        </label>
        <label class="form-field">
          <span>搜索</span>
          <input v-model.trim="keyword" type="search" placeholder="公司、岗位、来源、备注或简历（支持拼音/首字母）" />
        </label>
      </div>

      <p v-if="store.error" class="error-note" role="alert">{{ store.error }}</p>
      <div v-if="store.loading && !store.applications.length" class="loading-state">正在加载投递记录...</div>
      <EmptyState
        v-else-if="!filteredApplications.length && !store.error"
        :title="store.applications.length ? '没有符合筛选条件的记录' : '暂无投递记录'"
        :description="store.applications.length ? '调整状态或搜索词后重试。' : '添加第一条投递，记录求职进展。'"
      />
      <div v-else-if="filteredApplications.length" class="application-record-list">
        <section v-for="group in groupedApplications" :key="group.company" class="application-company-group">
          <h3 class="application-company-group-title">{{ group.company }}</h3>
          <article v-for="application in group.applications" :key="application.id" class="application-record">
          <div class="application-record-main">
            <div class="application-record-title">
              <strong :title="application.position">{{ application.position }}</strong>
            </div>
            <div class="application-record-details">
              <span :class="['application-status-pill', statusTone(application.status)]" :title="latestEventText(application)">
                {{ applicationStatusLabel(application.status) }}
              </span>
              <dl class="application-record-meta">
                <div>
                  <dt>投递</dt>
                  <dd>{{ formatDay(application.appliedDate) }}</dd>
                </div>
                <div>
                  <dt>简历</dt>
                  <dd :title="submissionLabel(application)">{{ submissionLabel(application) }}</dd>
                </div>
                <div>
                  <dt>来源</dt>
                  <dd :title="application.source || '未记录'">{{ application.source || '未记录' }}</dd>
                </div>
              </dl>
            </div>
            <div class="application-record-actions">
              <a v-if="application.jobUrl" class="action-button" :href="application.jobUrl" target="_blank" rel="noreferrer">
                <ExternalLink class="app-icon" aria-hidden="true" />
                <span>打开</span>
              </a>
              <button v-else class="action-button application-open-placeholder" type="button" disabled aria-hidden="true" tabindex="-1">
                <ExternalLink class="app-icon" aria-hidden="true" />
                <span>打开</span>
              </button>
              <button v-if="application.submittedSnapshot" class="action-button" type="button" :disabled="startingInterview !== null" @click="startInterview(application.id)"><span>{{ startingInterview === application.id ? '正在开始…' : '模拟面试' }}</span></button>
              <button v-if="application.submittedSnapshot" class="action-button" type="button" @click="toggleSubmission(application.id)"><span>{{ expandedSubmissions.has(application.id) ? '收起提交时材料' : '查看提交时材料' }}</span></button>
              <button class="action-button" type="button" @click="startEdit(application)">
                <Pencil class="app-icon" aria-hidden="true" />
                <span>编辑</span>
              </button>
              <button class="action-button" type="button" @click="startStatusEvent(application.id)">
                <CircleDot class="app-icon" aria-hidden="true" />
                <span>记录</span>
              </button>
              <button class="action-button" type="button" @click="startSchedule(application)">
                <CalendarDays class="app-icon" aria-hidden="true" />
                <span>日程</span>
              </button>
              <button type="button" @click="toggleTimeline(application.id)">
                <ListTree class="app-icon" aria-hidden="true" />
                <span>{{ expandedIds.has(application.id) ? '收起' : '时间线' }}</span>
              </button>
              <button type="button" class="danger-text" @click="removeApplication(application.id)">
                <Trash2 class="app-icon" aria-hidden="true" />
                <span>删除</span>
              </button>
            </div>
          </div>

          <section v-if="application.submittedSnapshot && expandedSubmissions.has(application.id)" class="submission-history" aria-label="提交时材料">
            <div class="section-head"><div><h3>提交时材料</h3><p>{{ submissionLabel(application) }} · {{ formatDateTime(application.submittedSnapshot.submittedAt) }}</p></div><RouterLink class="button-secondary" :to="`/resume-versions/${application.submittedSnapshot.resumeVersionId}`">查看确认版本</RouterLink></div>
            <p class="submission-history-note">以下正文保留自关联时，不随主简历更新。</p>
            <ResumePreview :resume="confirmedContent(application.submittedSnapshot.structuredContent)" title="提交时的简历正文" />
          </section>
          <div v-if="editingId === application.id" class="inline-form-panel application-entry-panel">
            <div class="section-head compact">
              <div>
                <h3>编辑投递</h3>
                <p>记录公司、岗位、投递日期、关联简历和当前进展。</p>
              </div>
            </div>

            <form class="application-form application-edit-form" @submit.prevent="submitApplication">
              <label class="form-field application-field application-company">
                <span>公司</span>
                <input v-model.trim="form.company" required placeholder="例如：字节跳动" />
              </label>
              <label class="form-field application-field application-position">
                <span>岗位</span>
                <input v-model.trim="form.position" required placeholder="例如：后端开发工程师" />
              </label>
              <label class="form-field application-field application-date">
                <span>投递日期</span>
                <input v-model="form.applied_date" required type="date" />
              </label>
              <div v-if="application.submittedSnapshot" class="form-field application-field application-resume submission-fixed"><span>提交时材料</span><strong>{{ submissionLabel(application) }}</strong><small>已固定，编辑记录不会更换材料。</small></div>
              <label v-else class="form-field application-field application-resume">
                <span>关联简历</span>
                <select v-model="form.resume_id">
                  <option :value="null">不关联</option>
                  <option v-for="resume in parsedResumes" :key="resume.id" :value="resumeNumericId(resume.id)">
                    {{ resume.filename }}
                  </option>
                </select>
              </label>
              <label class="form-field application-field application-link">
                <span>投递链接</span>
                <input v-model.trim="form.job_url" type="url" placeholder="https://..." />
              </label>
              <label class="form-field application-field application-source">
                <span>来源</span>
                <input v-model.trim="form.source" placeholder="官网 / Boss / 内推 / 猎头" />
              </label>
              <label class="form-field application-field application-notes">
                <span>备注</span>
                <input v-model.trim="form.notes" placeholder="简历版本、联系人、下一步动作等" />
              </label>
              <div class="form-actions application-edit-actions">
                <button class="button-secondary" type="button" :disabled="store.saving" @click="resetForm">
                  <X class="app-icon" aria-hidden="true" />
                  <span>取消</span>
                </button>
                <button class="button-primary" type="submit" :disabled="store.saving">
                  <Save class="app-icon" aria-hidden="true" />
                  <span>{{ store.saving ? '保存中...' : '保存' }}</span>
                </button>
              </div>
            </form>

            <p v-if="store.error" class="error-note">{{ store.error }}</p>
          </div>

          <form
            v-if="statusDraft.applicationId === application.id"
            class="inline-form-panel status-event-form"
            @submit.prevent="submitStatusEvent(application.id)"
          >
            <label>
              <span>新状态</span>
              <select v-model="statusDraft.status">
                <option v-for="item in applicationStatusOptions" :key="item.value" :value="item.value">
                  {{ item.label }}
                </option>
              </select>
            </label>
            <label>
              <span>发生时间</span>
              <input v-model="statusDraft.changed_at" type="datetime-local" />
            </label>
            <label class="span-two">
              <span>记录</span>
              <input v-model.trim="statusDraft.note" placeholder="例如：一面已约 / 笔试完成" />
            </label>
            <div class="form-actions">
              <button class="button-secondary" type="button" :disabled="store.saving" @click="clearStatusDraft">
              <X class="app-icon" aria-hidden="true" />
              <span>取消</span>
            </button>
              <button class="button-primary" type="submit" :disabled="store.saving">
              <Save class="app-icon" aria-hidden="true" />
              <span>保存</span>
            </button>
            </div>
          </form>

          <form
            v-if="scheduleDraft.applicationId === application.id"
            class="inline-form-panel status-event-form schedule-event-form"
            @submit.prevent="submitSchedule(application.id)"
          >
            <label>
              <span>日程类型</span>
              <select v-model="scheduleDraft.status">
                <option v-for="item in scheduleStatusOptions" :key="item.value" :value="item.value">
                  {{ item.label }}
                </option>
              </select>
            </label>
            <label>
              <span>标题</span>
              <input v-model.trim="scheduleDraft.title" required placeholder="例如：在线笔试 / 一面" />
            </label>
            <label>
              <span>开始</span>
              <input v-model="scheduleDraft.starts_at" required type="datetime-local" />
            </label>
            <label>
              <span>结束</span>
              <input v-model="scheduleDraft.ends_at" required type="datetime-local" />
            </label>
            <label class="span-two">
              <span>备注</span>
              <input v-model.trim="scheduleDraft.note" placeholder="会议链接、准备事项等" />
            </label>
            <div class="form-actions">
              <button class="button-secondary" type="button" :disabled="store.saving" @click="clearScheduleDraft">
              <X class="app-icon" aria-hidden="true" />
              <span>取消</span>
            </button>
              <button class="button-primary" type="submit" :disabled="store.saving">
              <Save class="app-icon" aria-hidden="true" />
              <span>保存</span>
            </button>
            </div>
          </form>

          <div v-if="expandedIds.has(application.id)" class="application-timeline">
            <div v-for="event in application.statusEvents" :key="event.id" class="application-timeline-item">
              <span :class="['timeline-dot', statusTone(event.status)]"></span>
              <strong>{{ applicationStatusLabel(event.status) }}</strong>
              <time>{{ formatDateTime(event.changedAt) }}</time>
              <p>{{ event.note || '无备注' }}</p>
            </div>
          </div>
          </article>
        </section>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { buildSearchIndex, matchesSearch } from '../utils/search'
import { ArrowLeft, ArrowRight, CalendarDays, ChevronLeft, ChevronRight, CircleDot, ExternalLink, ListTree, Pencil, Plus, Save, Trash2, X } from '@lucide/vue'
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { fetchResumeVersion } from '../api/resumeVersions'
import { createInterview } from '../api/interviews'
import { useAuthStore } from '../stores/auth'
import type { ResumeVersionArtifact } from '../api/agentRuns'
import { decisionsFor, projectResume, reviewChanges } from '../utils/resumeReview'
import ResumePreview from '../components/resume/ResumePreview.vue'
import EmptyState from '../components/EmptyState.vue'
import { useApplicationStore } from '../stores/application'
import { useDocumentStore } from '../stores/document'
import {
  applicationStatusLabel,
  applicationStatusOptions,
  type ApplicationStatus,
  type JobApplicationPayload,
  type JobApplicationRecord,
} from '../types/application'
import { applicationMatchesStatusFilter, applicationStatusFilterOptions, buildApplicationStatusSegments, buildApplicationSummary, buildApplicationMetricRecords, type ApplicationStatusFilter, type ApplicationMetricKey } from '../utils/applicationChart'
import { groupApplicationsByCompany } from '../utils/applicationGrouping'
import {
  buildApplicationScheduleItems,
  buildScheduleCalendarDays,
  buildScheduleNoteParts,
  formatDateTimeRange,
  formatLocalDateKey,
  getScheduleCalendarCategory,
  isScheduleToday,
  type ScheduleCalendarDay,
  type ApplicationScheduleItem,
} from '../utils/applicationSchedule'

const store = useApplicationStore()
const documentStore = useDocumentStore()
const auth = useAuthStore()
const startingInterview = ref<number | null>(null), interviewError = ref('')
const interviewRequests = new Map<number, string>()
let interviewPageActive = true
onBeforeUnmount(() => { interviewPageActive = false })
watch(() => auth.token, () => {
  interviewRequests.clear(); startingInterview.value = null; interviewError.value = ''
  try { for (const key of Object.keys(sessionStorage)) if (key.startsWith('resumate:interview:start:')) sessionStorage.removeItem(key) } catch { /* Keep in-memory behavior when browser storage is unavailable. */ }
})
async function startInterview(applicationId: number) {
  if (startingInterview.value !== null) return
  const token = auth.token
  const storageKey = `resumate:interview:start:${auth.username}:${applicationId}`
  let requestId = interviewRequests.get(applicationId)
  try { requestId ||= sessionStorage.getItem(storageKey) || undefined } catch { /* The in-memory request still prevents double clicks. */ }
  requestId ||= crypto.randomUUID()
  interviewRequests.set(applicationId, requestId)
  try { sessionStorage.setItem(storageKey, requestId) } catch { /* A refresh cannot restore a request when storage is disabled. */ }
  startingInterview.value = applicationId; interviewError.value = ''
  try {
    const result = await createInterview(applicationId, requestId)
    if (!interviewPageActive || auth.token !== token) return
    interviewRequests.delete(applicationId)
    try { sessionStorage.removeItem(storageKey) } catch { /* No persisted request to clear. */ }
    await router.push(`/interviews/${result.interviewId}`)
  } catch (cause) { if (interviewPageActive && auth.token === token) interviewError.value = cause instanceof Error ? cause.message : '未能开始练习，请重试' }
  finally { if (interviewPageActive && auth.token === token) startingInterview.value = null }
}
const route = useRoute(), router = useRouter()
const submissionVersionId = computed(() => String(route.query.resumeVersionId || ''))
const selectedVersion = ref<ResumeVersionArtifact | null>(null)
const submissionLoading = ref(false), submissionError = ref(''), submissionNotice = ref('')
const existingApplicationId = ref<number | ''>('')
const expandedSubmissions = ref<Set<number>>(new Set())
const availableSubmissions = computed(() => store.applications.filter(item => !item.submittedSnapshot || item.resumeVersionId === selectedVersion.value?.id))
let selectionGeneration = 0
watch([submissionVersionId, () => route.query.jdId], async ([id, jdId]) => {
  const generation = ++selectionGeneration
  selectedVersion.value = null; submissionError.value = ''; existingApplicationId.value = ''
  submissionLoading.value = Boolean(id)
  if (!id) return
  try {
    const version = await fetchResumeVersion(id)
    if (generation !== selectionGeneration) return
    if (version.status !== 'confirmed') throw new Error('请先确认简历版本，再关联投递。')
    if (Number(jdId) !== version.jdId) throw new Error('所选岗位与简历版本不一致，请从确认版本重新进入。')
    selectedVersion.value = version
  } catch (cause) { if (generation === selectionGeneration) submissionError.value = cause instanceof Error ? cause.message : '无法读取确认版本，请重试' }
  finally { if (generation === selectionGeneration) submissionLoading.value = false }
}, { immediate: true })
function confirmedContent(structuredContent: Record<string, unknown>) {
  const artifact = { structuredContent }
  const changes = reviewChanges(artifact)
  if (!changes) return structuredContent.resume && typeof structuredContent.resume === 'object' && !Array.isArray(structuredContent.resume) ? structuredContent.resume as Record<string, unknown> : structuredContent
  return projectResume(artifact, decisionsFor(changes))
}
function submissionLabel(application: JobApplicationRecord) {
  return application.submittedSnapshot ? `已确认版本 · 第 ${application.submittedSnapshot.revision} 版` : application.resumeFilename || '未关联'
}
function toggleSubmission(id: number) {
  const next = new Set(expandedSubmissions.value)
  if (next.has(id)) next.delete(id); else next.add(id)
  expandedSubmissions.value = next
}
async function clearSubmissionSelection() {
  const { resumeVersionId: _version, jdId: _jd, ...query } = route.query
  await router.replace({ query })
}
async function beginNewSubmission() {
  if (store.saving || !selectedVersion.value) return
  resetForm(); clearStatusDraft(); clearScheduleDraft()
  showApplicationForm.value = true
  await nextTick()
  document.querySelector('.application-entry-panel')?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
}
async function attachExistingSubmission() {
  if (store.saving || !selectedVersion.value || !existingApplicationId.value) return
  try {
    const id = Number(existingApplicationId.value)
    await store.attachSubmission(id, selectedVersion.value.jdId, selectedVersion.value.id)
    submissionNotice.value = '投递材料已关联，提交时的正文已保存。'
    resetForm()
    await clearSubmissionSelection()
  } catch { /* Keep the selected material and record for retry. */ }
}
const metricDialog = ref<HTMLDialogElement | null>(null)
const selectedMetric = ref<{ key: ApplicationMetricKey; label: string } | null>(null)
const metricDetailRecords = computed(() => selectedMetric.value
  ? buildApplicationMetricRecords(store.applications)[selectedMetric.value.key]
  : { total: [], inProgress: [] })
const metricActiveIds = computed(() => new Set(metricDetailRecords.value.inProgress.map((item) => item.id)))
const metricCompanyGroups = computed(() => groupApplicationsByCompany(metricDetailRecords.value.total, metricActiveIds.value))

function openMetricDetails(key: ApplicationMetricKey, label: string) {
  selectedMetric.value = { key, label }
  metricDialog.value?.showModal()
}

function closeMetricDetails() {
  metricDialog.value?.close()
}

const statusFilter = ref<ApplicationStatusFilter>('all')
const keyword = ref('')
const editingId = ref<number | null>(null)
const showApplicationForm = ref(false)
const exporting = ref(false)
const exportError = ref('')
const expandedIds = ref<Set<number>>(new Set())
const completingScheduleIds = ref<Set<number>>(new Set())
const initialCalendarDate = new Date()
const calendarMonth = ref(new Date(initialCalendarDate.getFullYear(), initialCalendarDate.getMonth(), 1))
const selectedDateKey = ref(formatLocalDateKey(initialCalendarDate))
const form = reactive<JobApplicationPayload>(emptyForm())
const statusDraft = reactive({
  applicationId: null as number | null,
  status: 'assessment' as ApplicationStatus,
  changed_at: localDateTimeInput(new Date()),
  note: '',
})
const scheduleDraft = reactive({
  applicationId: null as number | null,
  status: 'written_test' as ApplicationStatus,
  title: '在线笔试',
  starts_at: localDateTimeInput(new Date()),
  ends_at: localDateTimeInput(new Date(Date.now() + 60 * 60 * 1000)),
  note: '',
})

const parsedResumes = computed(() => documentStore.parsedResumes)
const statusSegments = computed(() => buildApplicationStatusSegments(store.applications))
const applicationSummary = computed(() => buildApplicationSummary(store.applications))
const stageMetrics = computed(() => [
  { key: 'assessment' as const, label: '测评', count: applicationSummary.value.assessmentCount, activeCount: applicationSummary.value.inProgress.assessmentCount, tone: 'active' },
  { key: 'writtenTest' as const, label: '笔试', count: applicationSummary.value.writtenTestCount, activeCount: applicationSummary.value.inProgress.writtenTestCount, tone: 'active' },
  { key: 'interview' as const, label: '面试', count: applicationSummary.value.interviewCount, activeCount: applicationSummary.value.inProgress.interviewCount, tone: 'active' },
  { key: 'rejected' as const, label: '已挂', count: applicationSummary.value.rejectedCount, tone: 'rejected' },
  { key: 'passed' as const, label: '通过', count: applicationSummary.value.passedCount, tone: 'passed' },
].map((metric) => ({
  ...metric,
  percent: store.totalCount ? Math.round(metric.count / store.totalCount * 100) : 0,
})))
const scheduleItems = computed(() => buildApplicationScheduleItems(store.applications))
const calendarDays = computed(() => buildScheduleCalendarDays(scheduleItems.value, calendarMonth.value))
const selectedCalendarDay = computed(() => calendarDays.value.find((day) => day.key === selectedDateKey.value))
const selectedDateSchedules = computed(() => selectedCalendarDay.value?.schedules ?? [])
const calendarMonthLabel = computed(() => new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric',
  month: 'long',
}).format(calendarMonth.value))
const selectedDateLabel = computed(() => {
  if (!selectedCalendarDay.value) return ''
  return new Intl.DateTimeFormat('zh-CN', {
    month: 'long',
    day: 'numeric',
    weekday: 'long',
  }).format(selectedCalendarDay.value.date)
})
const calendarWeekdays = ['一', '二', '三', '四', '五', '六', '日']
const scheduleStatusOptions = applicationStatusOptions.filter((item) =>
  ['assessment', 'written_test', 'interviewing', 'first_interview', 'second_interview', 'third_interview', 'hr_interview'].includes(item.value),
)

function changeCalendarMonth(offset: number) {
  const nextMonth = new Date(calendarMonth.value.getFullYear(), calendarMonth.value.getMonth() + offset, 1)
  calendarMonth.value = nextMonth
  const today = new Date()
  selectedDateKey.value = today.getFullYear() === nextMonth.getFullYear() && today.getMonth() === nextMonth.getMonth()
    ? formatLocalDateKey(today)
    : formatLocalDateKey(nextMonth)
}

function goToCurrentMonth() {
  const today = new Date()
  calendarMonth.value = new Date(today.getFullYear(), today.getMonth(), 1)
  selectedDateKey.value = formatLocalDateKey(today)
}

function selectCalendarDay(day: ScheduleCalendarDay) {
  selectedDateKey.value = day.key
  if (!day.isCurrentMonth) calendarMonth.value = new Date(day.date.getFullYear(), day.date.getMonth(), 1)
}

function calendarDayAriaLabel(day: ScheduleCalendarDay) {
  const date = new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' }).format(day.date)
  return `${date}，${day.schedules.length} 项日程`
}

const searchableApplications = computed(() => store.applications.map((application) => ({
  application,
  index: buildSearchIndex([
    application.company,
    application.position,
    application.source,
    application.notes,
    application.resumeFilename,
  ]),
})))

const filteredApplications = computed(() => {
  return searchableApplications.value.filter(({ application, index }) => {
    const statusMatched = applicationMatchesStatusFilter(application, statusFilter.value)
    const keywordMatched = matchesSearch(index, keyword.value)
    return statusMatched && keywordMatched
  }).map(({ application }) => application)
})
const groupedApplications = computed(() => groupApplicationsByCompany(filteredApplications.value))

async function exportRecords() {
  if (store.loading || exporting.value || !store.applications.length) return
  exporting.value = true
  exportError.value = ''
  try {
    const { createApplicationExportBlob } = await import('../utils/applicationExport')
    const blob = await createApplicationExportBlob(store.applications)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `投递记录-${formatLocalDateKey(new Date())}.xlsx`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  } catch (err) {
    exportError.value = `导出失败：${err instanceof Error ? err.message : String(err)}`
  } finally {
    exporting.value = false
  }
}

onMounted(async () => {
  await Promise.all([store.loadApplications(), documentStore.loadDocuments()])
})

async function submitApplication() {
  if (store.saving) return
  try {
    if (editingId.value) {
      const { status: _status, ...payload } = form
      await store.updateApplication(editingId.value, payload)
      resetForm()
      return
    }
    const version = selectedVersion.value
    await store.createApplication({ ...form, ...(version ? { resume_id: version.resumeId, jd_id: version.jdId, resume_version_id: version.id } : {}) })
    resetForm()
    if (version) {
      submissionNotice.value = '投递记录已添加，提交时的正文已保存。'
      await clearSubmissionSelection()
    }
  } catch {
    // The store exposes the request error; keep this form open with its draft.
  }
}
function startEdit(application: JobApplicationRecord) {
  if (store.saving) return
  clearStatusDraft()
  clearScheduleDraft()
  editingId.value = application.id
  showApplicationForm.value = false
  Object.assign(form, {
    company: application.company,
    position: application.position,
    applied_date: application.appliedDate,
    resume_id: application.resumeId,
    status: application.status,
    job_url: application.jobUrl,
    source: application.source,
    notes: application.notes,
  })
}

function resetForm() {
  editingId.value = null
  showApplicationForm.value = false
  Object.assign(form, emptyForm())
}

function toggleApplicationForm() {
  if (store.saving) return
  clearStatusDraft()
  clearScheduleDraft()
  if (showApplicationForm.value) {
    resetForm()
    return
  }
  editingId.value = null
  Object.assign(form, emptyForm())
  showApplicationForm.value = true
}

function startStatusEvent(applicationId: number) {
  if (store.saving) return
  resetForm()
  clearScheduleDraft()
  statusDraft.applicationId = applicationId
  statusDraft.status = 'assessment'
  statusDraft.changed_at = localDateTimeInput(new Date())
  statusDraft.note = ''
}

async function submitStatusEvent(applicationId: number) {
  if (store.saving) return
  try {
    await store.createStatusEvent(applicationId, {
      status: statusDraft.status,
      changed_at: new Date(statusDraft.changed_at).toISOString(),
      note: statusDraft.note,
    })
    clearStatusDraft()
    expandTimeline(applicationId)
  } catch {
    // The store exposes the request error; keep this form open with its draft.
  }
}
function clearStatusDraft() {
  statusDraft.applicationId = null
  statusDraft.note = ''
}

function startSchedule(application: JobApplicationRecord) {
  if (store.saving) return
  resetForm()
  clearStatusDraft()
  const start = new Date(Date.now() + 60 * 60 * 1000)
  const end = new Date(start.getTime() + 60 * 60 * 1000)
  scheduleDraft.applicationId = application.id
  scheduleDraft.status = nextScheduleStatus(application)
  scheduleDraft.title = applicationStatusLabel(scheduleDraft.status)
  scheduleDraft.starts_at = localDateTimeInput(start)
  scheduleDraft.ends_at = localDateTimeInput(end)
  scheduleDraft.note = ''
}

async function submitSchedule(applicationId: number) {
  if (store.saving) return
  try {
    const startsAt = new Date(scheduleDraft.starts_at)
    const endsAt = new Date(scheduleDraft.ends_at)
    if (endsAt <= startsAt) {
      window.alert('结束时间需要晚于开始时间')
      return
    }
    await store.createSchedule(applicationId, {
      status: scheduleDraft.status,
      title: scheduleDraft.title,
      starts_at: startsAt.toISOString(),
      ends_at: endsAt.toISOString(),
      note: scheduleDraft.note,
    })
    clearScheduleDraft()
  } catch {
    // The store exposes the request error; keep this form open with its draft.
  }
}
async function completeSchedule(schedule: ApplicationScheduleItem) {
  if (isCompletingSchedule(schedule.id) || schedule.isCompleted) return
  completingScheduleIds.value = new Set(completingScheduleIds.value).add(schedule.id)
  try {
    await store.completeSchedule(schedule.applicationId, schedule.id)
    expandTimeline(schedule.applicationId)
  } catch (err) {
    store.error = err instanceof Error ? err.message : String(err)
  } finally {
    const next = new Set(completingScheduleIds.value)
    next.delete(schedule.id)
    completingScheduleIds.value = next
  }
}

function isCompletingSchedule(scheduleId: number) {
  return completingScheduleIds.value.has(scheduleId)
}

function clearScheduleDraft() {
  scheduleDraft.applicationId = null
  scheduleDraft.note = ''
}

function nextScheduleStatus(application: JobApplicationRecord): ApplicationStatus {
  if (scheduleStatusOptions.some((item) => item.value === application.status)) return application.status
  return 'written_test'
}

function toggleTimeline(id: number) {
  const next = new Set(expandedIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expandedIds.value = next
}

function expandTimeline(id: number) {
  expandedIds.value = new Set(expandedIds.value).add(id)
}

async function removeApplication(id: number) {
  if (!window.confirm('确定删除这条投递记录吗？')) return
  await store.deleteApplication(id)
}

function emptyForm(): JobApplicationPayload {
  return {
    company: '',
    position: '',
    applied_date: formatLocalDateKey(new Date()),
    resume_id: null,
    status: 'applied',
    job_url: '',
    source: '',
    notes: '',
  }
}

function resumeNumericId(documentId: string) {
  return Number(documentId.split(':')[1] || 0)
}

function latestEventText(application: JobApplicationRecord) {
  const event = application.statusEvents[0]
  if (!event) return '无状态记录'
  return `${applicationStatusLabel(event.status)} · ${formatDateTime(event.changedAt)}${event.note ? ` · ${event.note}` : ''}`
}

function statusTone(status: ApplicationStatus) {
  if (status === 'passed' || status === 'offer') return 'success'
  if (status.includes('rejected') || status === 'withdrawn') return 'danger'
  if (status === 'applied') return 'muted'
  return 'info'
}

function scheduleTone(schedule: ApplicationScheduleItem) {
  if (schedule.completedEventId) return 'completed'
  if (isScheduleToday(schedule)) return 'today'
  return 'upcoming'
}

function scheduleNoteParts(note: string) {
  return buildScheduleNoteParts(note)
}

function formatDay(value: string) {
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date(`${value}T00:00:00`))
}

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

function localDateTimeInput(date: Date) {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000)
  return local.toISOString().slice(0, 16)
}
</script>

<style scoped>
.submission-choice { display: grid; gap: 20px; border: 1px solid var(--color-primary-border); min-width: 0; overflow-wrap: anywhere; }
.submission-choice .section-head { margin: 0; align-items: flex-start; } .submission-choice h2 { color: var(--color-primary); font-size: 22px; line-height: 1.5; }
.submission-choice h3,.submission-history h3 { margin: 0; font-size: 15px; line-height: 1.6; } .submission-choice p,.submission-history p { margin: 6px 0 0; font-size: 13px; line-height: 1.8; color: var(--color-text-secondary); }
.submission-choice .error-note { color: var(--color-danger); }
.submission-choice .submission-eyebrow { margin: 0 0 8px; font-size: 12px; } .submission-choice a,.submission-history a { text-decoration: none; }
.submission-fixed { display: grid; gap: 6px; padding: 16px; border-radius: 8px; background: var(--color-primary-light); color: var(--color-primary); font-size: 13px; line-height: 1.7; min-width: 0; }
.submission-fixed strong { font-size: 13px; } .submission-fixed small { font-size: 12px; color: var(--color-text-secondary); } .submission-fixed p { margin: 0; }
.submission-options { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 24px; }
.submission-options > * { display: grid; align-content: start; justify-items: start; gap: 12px; border-top: 1px solid var(--color-border); padding-top: 20px; min-width: 0; }
.submission-options .form-field { width: 100%; min-width: 0; } .submission-options select { width: 100%; min-width: 0; } .submission-options p { margin: 0; }
.submission-preview { min-width: 0; } .submission-preview summary { font-size: 13px; line-height: 1.8; color: var(--color-primary); cursor: pointer; padding: 8px 0; } .submission-preview .resume-preview { margin-top: 12px; }
.submission-notice { border: 1px solid var(--color-primary-border); border-radius: 8px; background: var(--surface-panel); padding: 16px 20px; color: var(--color-success); font-size: 13px; line-height: 1.8; }
.submission-history { display: grid; gap: 16px; padding: 24px; margin-top: 20px; border-top: 1px solid var(--color-border); min-width: 0; overflow-wrap: anywhere; } .submission-history .section-head { margin: 0; }
@media (max-width: 767px) { .application-record-main .application-record-actions { justify-self: stretch; flex-wrap: wrap; overflow-x: visible; } .application-record-main .application-open-placeholder { display: none; } .submission-choice { padding: 20px; } .submission-choice h2 { font-size: 20px; } .submission-options { grid-template-columns: minmax(0, 1fr); gap: 20px; } .submission-history { padding: 16px 0 0; } .submission-choice .section-head,.submission-history .section-head { flex-direction: column; gap: 12px; align-items: flex-start; } }
</style>
