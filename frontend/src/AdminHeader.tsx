import { useEffect, useState } from 'react'
import { request } from './api'

export function AdminHeader({ section, username, onLogout }: { section: 'members' | 'competitions' | 'announcements' | 'status'; username: string; onLogout: () => void }) {
  const titles = { members: '會員管理', competitions: '比賽管理', announcements: '公告管理', status: '系統狀態' }
  const [backup, setBackup] = useState<{ state: string; last_success_at: string | null } | null>(null)
  useEffect(() => { let active = true; request<{ state: string; last_success_at: string | null }>('/api/admin/backup-status')
    .then(value => { if (active) setBackup(value) }).catch(() => { if (active) setBackup(null) })
    return () => { active = false }
  }, [])
  const last = backup?.last_success_at ? new Intl.DateTimeFormat('zh-TW', { dateStyle: 'short', timeStyle: 'short', timeZone: 'Asia/Taipei' }).format(new Date(backup.last_success_at)) : '尚無成功紀錄'
  const backupText = backup?.state === 'ok' ? `備份正常・${last}` : backup?.state === 'failed' ? `備份失敗・上次成功 ${last}` : backup?.state === 'stale' ? `備份逾期・上次成功 ${last}` : null
  return <header className="admin-header no-print">
    <div><p className="eyebrow">府城球館管理後台</p><h1>{titles[section]}</h1></div>
    <div className="admin-header-controls"><nav className="admin-nav" aria-label="管理功能">
      {([['members', '/admin'], ['competitions', '/admin/competitions'], ['announcements', '/admin/announcements'], ['status', '/admin/system/deployment-report']] as const).map(([key, href]) =>
        <a key={key} href={href} aria-current={section === key ? 'page' : undefined}>{titles[key]}</a>)}
    </nav><div className="admin-account"><span>{username}</span><a href="/admin/roster">會員分級名單</a><button className="secondary" onClick={onLogout}>登出</button></div>{backupText && <small className={`admin-backup ${backup?.state}`}>{backupText}</small>}</div>
  </header>
}
