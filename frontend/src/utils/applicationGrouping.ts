export interface ApplicationCompanyGroup<T extends { company: string }> {
  company: string
  applications: T[]
}

export function groupApplicationsByCompany<T extends { company: string; id: number }>(
  applications: T[],
  inProgressIds?: ReadonlySet<number>,
): ApplicationCompanyGroup<T>[] {
  const groups = applications.reduce<ApplicationCompanyGroup<T>[]>((groups, application) => {
    const company = application.company.trim()
    const group = groups.find((item) => item.company === company)
    if (group) group.applications.push(application)
    else groups.push({ company, applications: [application] })
    return groups
  }, [])
  if (inProgressIds) {
    groups.sort((a, b) =>
      Number(b.applications.some((item) => inProgressIds.has(item.id)))
      - Number(a.applications.some((item) => inProgressIds.has(item.id))),
    )
  }
  return groups
}
