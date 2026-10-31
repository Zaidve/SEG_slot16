export function plural(count, word) {
  return `${count} ${word}${count === 1 ? '' : 's'}`
}

export function formatDate(value) {
  return new Date(value).toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}
