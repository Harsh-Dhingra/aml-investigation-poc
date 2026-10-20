import { useEffect, useMemo, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { fetchCustomerKyc, type CustomerKyc as KycData } from '../api'
import { ErrorState, Spinner } from '../components/ui'
import ActivityTab from '../kyc/ActivityTab'
import CounterpartiesTab from '../kyc/CounterpartiesTab'
import CustomerHeader from '../kyc/CustomerHeader'
import { TABS, profileExceptions, type TabKey } from '../kyc/exceptions'
import HistoryTab from '../kyc/HistoryTab'
import ProfileTab from '../kyc/ProfileTab'
import TransactionsTab from '../kyc/TransactionsTab'

export default function CustomerKyc() {
  const { customerId = '' } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const [data, setData] = useState<KycData | null>(null)
  const [error, setError] = useState<string | null>(null)

  const requested = searchParams.get('tab') as TabKey | null
  const tab: TabKey = TABS.some((t) => t.key === requested) ? requested! : 'profile'
  const setTab = (t: TabKey) => setSearchParams(t === 'profile' ? {} : { tab: t }, { replace: true })

  useEffect(() => {
    setData(null)
    setError(null)
    fetchCustomerKyc(customerId).then(setData).catch((e: Error) => setError(e.message))
  }, [customerId])

  const exceptions = useMemo(() => (data ? profileExceptions(data) : []), [data])

  if (error) return <ErrorState message={error} />
  if (!data) return <Spinner label={`Loading KYC profile for ${customerId}...`} />

  return (
    <div>
      <CustomerHeader data={data} exceptions={exceptions} tab={tab} onTab={setTab} />
      <div className="mx-auto max-w-6xl px-8 py-6">
        {tab === 'profile' && <ProfileTab data={data} exceptions={exceptions} onTab={setTab} />}
        {tab === 'activity' && <ActivityTab data={data} />}
        {tab === 'transactions' && <TransactionsTab data={data} />}
        {tab === 'counterparties' && <CounterpartiesTab data={data} />}
        {tab === 'history' && <HistoryTab data={data} />}
      </div>
    </div>
  )
}
