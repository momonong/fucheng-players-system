import { useEffect } from 'react'
import { appUrl } from './paths'
import { helpImages } from './helpImages'

const memberSteps = [
  ['home', '先認識首頁', '首頁會顯示最新公告與比賽時程。上方可切換「會員分級表」「比賽報名」；隨時按「府城球館」就能回到首頁。'],
  ['members', '查詢會員分級', '按「會員分級表」，輸入姓名或辨識註記找到自己。也可以選擇級數查看名單；需要紙本時，按「列印／另存 PDF」。'],
  ['competitions', '選擇要參加的比賽', '按「比賽報名」，先確認場次、日期與截止時間，再開啟該場比賽。不同場次可能採個人報名或雙打組隊。'],
  ['individual', '個人賽：選名字，再送出', '搜尋並選取會員姓名，核對辨識註記，依畫面選擇本場餐食並完成真人驗證，再按確認送出。送出後請查看結果，確認是正取或候補。'],
  ['doubles', '雙打賽：單人等待，或兩人組隊', '可以先單人登記等待搭檔，也可以直接選兩位會員送出組隊。已有人等待時，可從等待名單選擇搭檔。送出後先列為待管理員確認；級數規則由管理員審核，送出不代表已成為正取。'],
  ['roster', '查看正取與候補名單', '進入該場比賽，往下找到「報名名單」，即可查看正取與候補姓名。同名者請核對註記；名單會自動更新，也可以按「更新名單」重新讀取。雙打賽也會列出等待搭檔與待管理員確認的隊伍。報名截止後仍能查看名單。'],
] as const
const adminSteps = [
  ['login', '從「更多」進入管理後台', '按導覽最右側的三條線選單，選擇「管理後台」，輸入自己的管理員帳號與密碼。操作完請登出；不要把帳密借給其他人。'],
  ['admin-members', '維護會員資料', '在會員管理中搜尋或新增會員，核對姓名、辨識註記與級數後儲存。同名會員請用辨識註記區分；停用不等於刪除。'],
  ['admin-competitions', '管理比賽與報名', '建立場次時確認日期、報名方式、名額與截止時間。個人賽可管理正取、候補及安排表；雙打賽請審核待確認組隊。安排或修改後記得儲存，再核對名單。'],
  ['admin-news', '儲存公告，再公開', '在公告管理新增或選取公告，先儲存標題與內容，再開啟「公開到首頁」。置頂可讓重要公告優先顯示；下架可關閉公開，刪除的公告可從已刪除清單還原。'],
] as const

export function HelpPage() {
  useEffect(() => { document.title = '使用說明｜府城球館' }, [])
  const sections = [{ id: 'members-help', title: '會員使用', intro: '查名單、查看比賽與協助其他人報名。', steps: memberSteps }, { id: 'admins-help', title: '管理員操作', intro: '只有管理員登入後，才能修改會員、比賽與公告。', steps: adminSteps }]
  return <main className="help-page">
    <header className="help-intro"><p className="section-kicker">使用指南</p><h1>跟著畫面，一步一步來。</h1><p>第一次使用也沒關係。選擇下面的說明，照著畫面操作就可以了。</p><nav aria-label="說明分類"><a href={`${appUrl('/help')}#members-help`}>會員使用 ↓</a><a href={`${appUrl('/help')}#admins-help`}>管理員操作 ↓</a></nav></header>
    <aside className="help-note"><strong>需要別人幫忙報名也可以。</strong><p>選名報名不代表身分驗證，請先和本人確認。找不到名字、需要取消或更正時，請洽球館管理員；不要重複送出報名。</p></aside>
    {sections.map(section => <section className="help-section" key={section.id} id={section.id}><header><h2>{section.title}</h2><p>{section.intro}</p></header><ol className="help-steps">{section.steps.map(([image, title, text], i) => <li className="help-step" key={image}><div className="help-step-copy"><span className="help-step-number" aria-hidden="true">{String(i + 1).padStart(2, '0')}</span><div><h3>{title}</h3><p>{text}</p></div></div><figure><a href={helpImages[image]} target="_blank" rel="noopener noreferrer" aria-label={`開啟大圖：${title}`}><img src={helpImages[image]} alt={`${title}的系統示範畫面`} loading="lazy" width={image === 'roster' ? 900 : 1440} height={image === 'roster' ? 500 : 1000} /></a><figcaption>示範畫面・姓名與場次僅供操作說明。點圖片可開啟大圖。</figcaption></figure></li>)}</ol></section>)}
    <aside className="help-note"><h2>給球館值班人員</h2><p>網站由球館電腦提供服務。請保持主機開機、網路連線及 Docker Desktop 運行；可以關螢幕，請不要關閉主機。需要重開機或維護時，先聯絡系統管理者。</p></aside>
    <p className="help-back"><a href={appUrl('/')}>← 返回最新消息</a></p>
  </main>
}
