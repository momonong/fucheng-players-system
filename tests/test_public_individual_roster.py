"""Anonymous lists disclose only the explicitly approved roster fields."""
from sqlalchemy import select
from fucheng.models import Admin, Competition, CompetitionRegistration, Member, now_utc
from test_competitions import _competition_payload, _member


def test_public_roster_order_privacy_closed_and_visibility(client, app, auth):
    comp = client.post('/api/admin/competitions', headers=auth, json=_competition_payload(capacity=1)).json()
    members = [_member(client, auth, i) for i in (701, 702, 703)]
    with app.state.session_factory.begin() as db:
        for i, member in enumerate(members):
            row = db.get(Member, member['id']); row.name = '陳先生'; row.distinguishing_note = ['老師', '學生', '已取消示範'][i]
            db.add(CompetitionRegistration(competition_id=comp['id'], member_id=row.id,
                status=['confirmed','waitlisted','cancelled'][i], diet='vegetarian',
                hard_level_snapshot=3, competition_level=4, queue_sequence=i+1,
                created_by_kind='admin', updated_by_kind='admin', created_by_admin_id=db.scalar(select(Admin.id)), updated_by_admin_id=db.scalar(select(Admin.id))))
    url=f"/api/public/competitions/{comp['id']}/registrations"
    response=client.get(url)
    assert response.status_code==200
    assert response.headers['cache-control']=='no-store'
    result=response.json()
    assert set(result)=={'competition','entries'}
    assert [(e['name'],e['distinguishing_note'],e['status'],e['queue_sequence']) for e in result['entries']]==[
        ('陳先生','老師','confirmed',1),('陳先生','學生','waitlisted',2)]
    assert all(set(e)=={'name','distinguishing_note','status','queue_sequence'} for e in result['entries'])
    for status in ['closed','draft','cancelled','open']:
        with app.state.session_factory.begin() as db: db.get(Competition,comp['id']).status=status
        visible=status in ('open','closed')
        assert client.get(url).status_code==(200 if visible else 404)
        listed=client.get('/api/public/registration-rosters').json()
        assert (comp['id'] in [c['id'] for c in listed])==visible
    with app.state.session_factory.begin() as db: db.get(Competition,comp['id']).deleted_at=now_utc()
    assert client.get(url).status_code==404
    assert not client.get('/api/public/registration-rosters').json()


def test_public_and_admin_registration_share_same_live_roster(client, app, auth):
    from test_competitions import _register
    from test_public_registration import visitor, register
    comp=client.post('/api/admin/competitions',headers=auth,json=_competition_payload(capacity=1)).json()
    members=[_member(client,auth,i) for i in (801,802)]
    visitor_client, headers=visitor(app)
    assert register(visitor_client,headers,comp,members[0]).status_code==201
    _register(client,auth,comp['id'],members[1]['id'])
    url=f"/api/public/competitions/{comp['id']}/registrations"
    entries=visitor_client.get(url).json()['entries']
    assert [(r['name'],r['status']) for r in entries]==[(members[0]['name'],'confirmed'),(members[1]['name'],'waitlisted')]
    # A read does not create a baseline, alter the roster, or write audits.
    with app.state.session_factory() as db:
        before=[(r.id,r.status,r.version,r.competition_level) for r in db.scalars(select(CompetitionRegistration).order_by(CompetitionRegistration.queue_sequence))]
    visitor_client.get(url);visitor_client.get('/api/public/registration-rosters')
    with app.state.session_factory() as db:
        after=[(r.id,r.status,r.version,r.competition_level) for r in db.scalars(select(CompetitionRegistration).order_by(CompetitionRegistration.queue_sequence))]
    assert before==after
