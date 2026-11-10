import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import App from '../App.vue'

describe('App', () => {
  it('앱 셸 제목을 렌더한다', () => {
    const wrapper = mount(App)
    expect(wrapper.get('h1').text()).toBe('나라장터 입찰 검색')
  })
})
