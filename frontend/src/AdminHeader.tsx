import { appUrl } from './paths'
import { useEffect, useState } from 'react'
import { request } from './api'

export function AdminHeader({ section, username, displayName, onLogout }: { section: 'members' | 'competitions' | 'announcements' | 'admins' | 'status' | 'roster'; username: string; displayName?: string | null; onLogout: () => void }) {
  const titles = { members: '會員管理', competitions: '比賽管理', announcements: '公告管理', admins: '管理員管理', status: '系統狀態', roster: '會員分級表' }
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
      {([['members', '/admin'], ['competitions', '/admin/competitions'], ['announcements', '/admin/announcements'], ['admins', '/admin/admins'], ['status', '/admin/system/deployment-report']] as const).map(([key, href]) =>
        <a key={key} href={appUrl(href)} aria-current={section === key ? 'page' : undefined}>{titles[key]}</a>)}
    </nav><div className="admin-account"><a className="mobile-home-link" href={appUrl('/')}>球館首頁</a><a href={appUrl("/admin/roster")} aria-current={section === 'roster' ? 'page' : undefined}>會員分級表</a><button className="secondary" onClick={onLogout}>登出</button></div><div className="admin-status-line">{backupText && <small className={`admin-backup ${backup?.state}`}>{backupText}</small>}<span className="admin-username" title={displayName ? `${displayName}（${username}）` : username}>{displayName ? `${displayName}（${username}）` : username}</span></div></div>
  </header>
}
