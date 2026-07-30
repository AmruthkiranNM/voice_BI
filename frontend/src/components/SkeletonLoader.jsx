/** Shimmer placeholder shaped like the results dashboard, shown while a query runs. */
export default function SkeletonLoader() {
  return (
    <div className="animate-in space-y-6">
      <div className="flex items-end justify-between gap-4 pb-5 border-b border-black/10">
        <div className="space-y-2">
          <div className="skeleton h-2.5 w-32" />
          <div className="skeleton h-6 w-72" />
        </div>
        <div className="skeleton h-8 w-20 rounded-full" />
      </div>

      <div className="panel-card p-0 overflow-hidden">
        <div className="grid grid-cols-2 sm:grid-cols-4 divide-x divide-black/5 border-b border-black/10">
          {[0, 1, 2, 3].map(i => (
            <div key={i} className="p-5 space-y-2.5">
              <div className="skeleton h-2.5 w-16" />
              <div className="skeleton h-7 w-20" />
            </div>
          ))}
        </div>
        <div className="p-6">
          <div className="skeleton h-52 w-full" />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[3fr_2fr] gap-6">
        <div className="panel-card space-y-3">
          <div className="skeleton h-2.5 w-20" />
          <div className="skeleton h-4 w-full" />
          <div className="skeleton h-4 w-5/6" />
          <div className="skeleton h-4 w-2/3" />
        </div>
        <div className="panel-card space-y-3">
          <div className="skeleton h-2.5 w-20" />
          <div className="skeleton h-14 w-full" />
          <div className="skeleton h-14 w-full" />
        </div>
      </div>
    </div>
  );
}
